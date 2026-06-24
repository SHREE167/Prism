import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

import os
import re
import sys
import uuid
import shutil
import secrets
import threading
import time
from functools import wraps

from flask import (Flask, render_template, request, send_file,
                   flash, redirect, url_for, jsonify, session)
import yt_dlp
from dotenv import load_dotenv
from supabase import create_client, Client
from datetime import timedelta

from main import download_images

load_dotenv()

# ──────────────────────────────────────────────
# App Setup
# ──────────────────────────────────────────────

app = Flask(__name__)

# C5 FIX: Crash on startup if secret key is missing — never use a hardcoded fallback
secret_key = os.environ.get("FLASK_SECRET_KEY")
if not secret_key:
    sys.exit("FATAL: FLASK_SECRET_KEY environment variable is not set. Refusing to start with an insecure default.")
app.secret_key = secret_key
app.permanent_session_lifetime = timedelta(days=30)

# Initialize Supabase
supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_KEY")
if not supabase_url or not supabase_key:
    sys.exit("FATAL: SUPABASE_URL and SUPABASE_KEY environment variables must be set.")
supabase: Client = create_client(supabase_url, supabase_key)

# ── Directories ────────────────────────────────────────
VIDEO_DOWNLOAD_DIR = "videos"
IMAGE_DOWNLOAD_DIR = "images"
os.makedirs(VIDEO_DOWNLOAD_DIR, exist_ok=True)
os.makedirs(IMAGE_DOWNLOAD_DIR, exist_ok=True)

# C2 FIX: Use env var or auto-detect ffmpeg on PATH instead of hardcoded Windows path
FFMPEG_PATH = os.environ.get("FFMPEG_PATH") or shutil.which("ffmpeg")

# ──────────────────────────────────────────────
# Per-Session Download State (C3 FIX)
# ──────────────────────────────────────────────
# Replaces the old global download_state dict that was shared by ALL users.
# Now keyed by a UUID (download_id) stored in each user's session.
active_downloads = {}
downloads_lock = threading.Lock()
DOWNLOAD_TTL_SECONDS = 3600  # Cleanup stale entries after 1 hour


def create_download_entry():
    """Create a new per-session download state entry and return its ID."""
    download_id = str(uuid.uuid4())
    with downloads_lock:
        active_downloads[download_id] = {
            "progress": 0.0,
            "status": "idle",
            "message": "",
            "file_path": None,
            "error": None,
            "created_at": time.time(),
        }
    return download_id


def get_download_state(download_id):
    """Get a snapshot of the download state for the given ID."""
    with downloads_lock:
        entry = active_downloads.get(download_id)
        if entry:
            return dict(entry)
    return None


def cleanup_stale_downloads():
    """Remove download entries and their files older than TTL."""
    now = time.time()
    with downloads_lock:
        stale_ids = [
            did for did, state in active_downloads.items()
            if now - state.get("created_at", 0) > DOWNLOAD_TTL_SECONDS
        ]
        for did in stale_ids:
            state = active_downloads.pop(did, {})
            file_path = state.get("file_path")
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError:
                    pass


def cleanup_download_file(download_id):
    """Remove the downloaded file and state entry after it's been served (C4 FIX)."""
    with downloads_lock:
        state = active_downloads.pop(download_id, {})
    file_path = state.get("file_path")
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError:
            pass


# ──────────────────────────────────────────────
# Authentication (H2 FIX: saves intended URL)
# ──────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            # H2 FIX: Preserve the URL the user was trying to access
            session["next_url"] = request.url
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


# ──────────────────────────────────────────────
# CSRF Protection (H6 FIX)
# ──────────────────────────────────────────────
@app.before_request
def csrf_protect():
    """Validate CSRF token on all POST requests."""
    if request.method == "POST":
        token = session.get("csrf_token")
        form_token = request.form.get("csrf_token")
        if not token or token != form_token:
            flash("Session expired. Please try again.", "error")
            return redirect(request.referrer or url_for("index"))


@app.context_processor
def inject_csrf_token():
    """Make csrf_token available in all Jinja2 templates automatically."""
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return {"csrf_token": session["csrf_token"]}


# ──────────────────────────────────────────────
# Video Download Logic
# ──────────────────────────────────────────────
def run_download(download_id, url, format_id, output_template):
    """Runs yt-dlp in a background thread and writes progress to per-session state."""
    def progress_hook(d):
        if d["status"] == "downloading":
            percent_str = d.get("_percent_str", "")
            match = re.search(r"([0-9.]+)", percent_str)
            if match:
                try:
                    pct = float(match.group(1))
                    with downloads_lock:
                        state = active_downloads.get(download_id)
                        if state:
                            # Video + audio are two streams so cap video at 90%
                            state["progress"] = min(pct * 0.9, 90.0)
                            state["status"] = "downloading"
                            state["message"] = "Downloading..."
                except ValueError:
                    pass
        elif d["status"] == "finished":
            with downloads_lock:
                state = active_downloads.get(download_id)
                if state:
                    state["progress"] = 92.0
                    state["status"] = "merging"
                    state["message"] = "Merging audio & video..."

    ydl_opts = {
        "format": format_id,
        "outtmpl": output_template,
        "merge_output_format": "mp4",
        "progress_hooks": [progress_hook],
        "quiet": True,
        "no_warnings": True,
        # M4 FIX: Scope postprocessor_args to the merger for yt-dlp compatibility
        "postprocessor_args": {"merger": ["-c:a", "aac", "-b:a", "192k"]},
    }

    # C2 FIX: Only set ffmpeg_location if a path was found
    if FFMPEG_PATH:
        ydl_opts["ffmpeg_location"] = FFMPEG_PATH

    # For audio-only downloads: convert to high-quality 320kbps MP3
    if format_id == "bestaudio/best":
        ydl_opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "320",
        }]
        # MP3 output won't be .mp4
        ydl_opts.pop("merge_output_format", None)
        ydl_opts.pop("postprocessor_args", None)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url)
            base = ydl.prepare_filename(info)

            # Resolve actual output file
            if format_id == "bestaudio/best":
                final = os.path.splitext(base)[0] + ".mp3"
            else:
                final = os.path.splitext(base)[0] + ".mp4"

            if not os.path.exists(final):
                # fallback: find any file matching the UUID base
                base_no_ext = os.path.splitext(base)[0]
                for ext in [".mp4", ".mp3", ".webm", ".mkv", ".m4a"]:
                    candidate = base_no_ext + ext
                    if os.path.exists(candidate):
                        final = candidate
                        break

            with downloads_lock:
                state = active_downloads.get(download_id)
                if state:
                    state["progress"] = 100.0
                    state["status"] = "done"
                    state["message"] = "Download complete!"
                    state["file_path"] = final
    except Exception as e:
        with downloads_lock:
            state = active_downloads.get(download_id)
            if state:
                state["status"] = "error"
                state["error"] = str(e)
                state["message"] = f"Error: {e}"


# ──────────────────────────────────────────────
# Image Download Logic (H4 FIX: background thread)
# ──────────────────────────────────────────────
def run_image_download(download_id, query, count):
    """Runs image search + download in a background thread to avoid request timeouts."""
    try:
        with downloads_lock:
            state = active_downloads.get(download_id)
            if state:
                state["status"] = "downloading"
                state["message"] = f"Searching for '{query}'..."
                state["progress"] = 10.0

        download_images(query, save_dir=IMAGE_DOWNLOAD_DIR, max_results=count)

        clean_query = "".join(c if c.isalnum() else "_" for c in query)
        folder = os.path.join(IMAGE_DOWNLOAD_DIR, clean_query)

        with downloads_lock:
            state = active_downloads.get(download_id)
            if state:
                state["progress"] = 80.0
                state["message"] = "Creating zip file..."

        if os.path.exists(folder) and os.listdir(folder):
            zip_path = shutil.make_archive(
                os.path.join(IMAGE_DOWNLOAD_DIR, f"{clean_query}_images"), "zip", folder
            )
            with downloads_lock:
                state = active_downloads.get(download_id)
                if state:
                    state["progress"] = 100.0
                    state["status"] = "done"
                    state["message"] = "Images ready!"
                    state["file_path"] = zip_path
            # Clean up the source image folder after zipping
            shutil.rmtree(folder, ignore_errors=True)
        else:
            with downloads_lock:
                state = active_downloads.get(download_id)
                if state:
                    state["status"] = "error"
                    state["error"] = "No images found for that query."
                    state["message"] = "No images found."
    except Exception as e:
        with downloads_lock:
            state = active_downloads.get(download_id)
            if state:
                state["status"] = "error"
                state["error"] = str(e)
                state["message"] = f"Error: {e}"


# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if "user" in session:
        return redirect(url_for("index"))

    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        try:
            auth_response = supabase.auth.sign_in_with_password({"email": email, "password": password})

            if auth_response.user:
                session.permanent = True
                session["user"] = auth_response.user.id
                session["email"] = auth_response.user.email
                flash(f"Success! Logged in as {auth_response.user.email}", "success")
                # H2 FIX: Redirect to the page they were trying to access before login
                next_url = session.pop("next_url", None)
                return redirect(next_url or url_for("index"))
            else:
                flash("Login failed: Unknown authentication error.", "error")
        except Exception as e:
            error_data = str(e)
            if "Email not confirmed" in error_data:
                flash("Login blocked: Please check your inbox and verify your email address.", "error")
            elif "Invalid login credentials" in error_data:
                flash("Login failed: Incorrect email or password.", "error")
            else:
                flash(f"Login failed: {error_data}", "error")
            return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if "user" in session:
        return redirect(url_for("index"))

    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        try:
            signup_response = supabase.auth.sign_up({"email": email, "password": password})

            if signup_response.user and not signup_response.session:
                flash("Account created! Check your email to verify before logging in.", "success")
            else:
                flash("Sign up successful! You can now log in.", "success")

            return redirect(url_for("login"))
        except Exception as e:
            error_msg = str(e)
            if "already registered" in error_msg.lower():
                flash("An account with this email already exists.", "error")
            else:
                flash(f"Sign up failed: {error_msg}", "error")
            return redirect(url_for("signup"))

    return render_template("signup.html")


# H1 FIX: Clean logout — sign out from Supabase and clear session properly
@app.route("/logout")
def logout():
    try:
        supabase.auth.sign_out()
    except Exception:
        pass  # Best-effort sign out from Supabase
    session.clear()
    flash("You have been successfully logged out.", "success")
    return redirect(url_for("login"))


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html", user_email=session.get("email"))


@app.route("/video", methods=["POST"])
@login_required
def handle_video():
    url = request.form.get("url")
    action = request.form.get("action")

    if not url:
        flash("Please provide a valid YouTube URL.", "error")
        return redirect(url_for("index"))

    if action == "fetch":
        try:
            with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
                info = ydl.extract_info(url, download=False)
                formats = info.get("formats", [info])
                resolutions = set()
                has_audio = False

                for f in formats:
                    if f.get("ext") == "mhtml" or "storyboard" in f.get("format_note", "").lower():
                        continue
                    if f.get("vcodec") != "none" and f.get("height"):
                        resolutions.add(f.get("height"))
                    if f.get("acodec") != "none":
                        has_audio = True

                sorted_res = sorted(list(resolutions), reverse=True)
                simplified_formats = [
                    {"format_id": "bestvideo+bestaudio[ext=m4a]/bestvideo+bestaudio/best", "label": "Highest Available Quality (Default)"}
                ]

                for res in sorted_res:
                    simplified_formats.append({
                        "format_id": f"bestvideo[height<={res}]+bestaudio[ext=m4a]/bestvideo[height<={res}]+bestaudio/best[height<={res}]",
                        "label": f"{res}p Standard Video"
                    })

                if has_audio or not sorted_res:
                    simplified_formats.append({"format_id": "bestaudio/best", "label": "Audio Only (MP3/M4A)"})

            return render_template("index.html", url=url, formats=simplified_formats, active_tab="video", user_email=session.get("email"))
        except Exception as e:
            flash(f"Failed to fetch video details: {str(e)}", "error")
            return redirect(url_for("index"))

    elif action == "download":
        format_id = request.form.get("format")
        if not format_id:
            flash("Please select a format to download.", "error")
            return redirect(url_for("index"))

        # C3 FIX: Per-session download state
        cleanup_stale_downloads()
        download_id = create_download_entry()
        session["download_id"] = download_id

        temp_name = f"{uuid.uuid4()}.%(ext)s"
        output_template = os.path.join(VIDEO_DOWNLOAD_DIR, temp_name)

        t = threading.Thread(target=run_download, args=(download_id, url, format_id, output_template), daemon=True)
        t.start()

        return render_template("index.html", url=url, formats=[], active_tab="video", waiting=True, user_email=session.get("email"))


# H3 FIX: Added @login_required to both API endpoints
@app.route("/api/progress")
@login_required
def api_progress():
    """Frontend polls this endpoint every second."""
    download_id = session.get("download_id")
    if not download_id:
        return jsonify({"progress": 0, "status": "error", "message": "No active download", "error": "No active download"}), 404

    state = get_download_state(download_id)
    if not state:
        return jsonify({"progress": 0, "status": "error", "message": "Download expired", "error": "Download expired"}), 404

    return jsonify({
        "progress": state["progress"],
        "status": state["status"],
        "message": state["message"],
        "error": state["error"],
    })


@app.route("/api/download-file")
@login_required
def api_download_file():
    """Called by the frontend once status is 'done' to fetch the file."""
    download_id = session.get("download_id")
    if not download_id:
        return "No active download", 404

    state = get_download_state(download_id)
    if not state or state["status"] != "done" or not state.get("file_path"):
        return "File not ready", 404

    file_path = state["file_path"]
    if not os.path.exists(file_path):
        return "File not found", 404

    # C4 FIX: Schedule file cleanup after the response is sent
    response = send_file(file_path, as_attachment=True)

    @response.call_on_close
    def _cleanup():
        cleanup_download_file(download_id)

    session.pop("download_id", None)
    return response


# H4 FIX: Image download now runs in a background thread (same pattern as video)
# H5 FIX: Surfaces a clear error when the SerpAPI key is missing
@app.route("/images", methods=["POST"])
@login_required
def handle_images():
    query = request.form.get("query")
    count = request.form.get("count", 10, type=int)

    if not query:
        flash("Please provide a search query.", "error")
        return redirect(url_for("index"))

    # H5 FIX: Check for API key before starting download
    if not os.environ.get("API_KEY"):
        flash("Image search is currently unavailable (API key not configured).", "error")
        return redirect(url_for("index"))

    cleanup_stale_downloads()
    download_id = create_download_entry()
    session["download_id"] = download_id

    t = threading.Thread(target=run_image_download, args=(download_id, query, count), daemon=True)
    t.start()

    return render_template("index.html", active_tab="image", image_waiting=True, user_email=session.get("email"))


if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("[SUCCESS] Prism Media Fetcher Server Started!")
    print("[LINK]    CLICK HERE >>> http://127.0.0.1:5000/")
    print("=" * 50 + "\n")
    app.run(debug=True, port=5000, use_reloader=False)
