import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

from flask import Flask, render_template, request, send_file, flash, redirect, url_for, jsonify
import yt_dlp
import os
import uuid
import shutil
import re
import threading
from main import download_images

app = Flask(__name__)
app.secret_key = "super_secret_media_fetcher_key"

# Directories
VIDEO_DOWNLOAD_DIR = "videos"
IMAGE_DOWNLOAD_DIR = "images"

# FFMPEG path
FFMPEG_EXE_PATH = r"C:\Users\Shree\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin\ffmpeg.exe"

os.makedirs(VIDEO_DOWNLOAD_DIR, exist_ok=True)
os.makedirs(IMAGE_DOWNLOAD_DIR, exist_ok=True)

# --- Global Download State ---
download_state = {
    "progress": 0.0,
    "status": "idle",       # idle | downloading | merging | done | error
    "message": "",
    "file_path": None,
    "error": None,
}
download_lock = threading.Lock()


def reset_state():
    with download_lock:
        download_state["progress"] = 0.0
        download_state["status"] = "idle"
        download_state["message"] = ""
        download_state["file_path"] = None
        download_state["error"] = None


def run_download(url, format_id, output_template):
    """Runs yt-dlp in a background thread and writes progress to download_state."""
    def progress_hook(d):
        if d["status"] == "downloading":
            percent_str = d.get("_percent_str", "")
            match = re.search(r"([0-9.]+)", percent_str)
            if match:
                try:
                    pct = float(match.group(1))
                    with download_lock:
                        # Video + audio are two streams so cap video at 90%
                        download_state["progress"] = min(pct * 0.9, 90.0) 
                        download_state["status"] = "downloading"
                        download_state["message"] = "Downloading..."
                except ValueError:
                    pass
        elif d["status"] == "finished":
            with download_lock:
                download_state["progress"] = 92.0
                download_state["status"] = "merging"
                download_state["message"] = "Merging audio & video..."

    ydl_opts = {
        "format": format_id,
        "outtmpl": output_template,
        "merge_output_format": "mp4",
        "ffmpeg_location": FFMPEG_EXE_PATH,
        "progress_hooks": [progress_hook],
        "quiet": True,
        "no_warnings": True,
        # Force audio to AAC on merge — ensures audio works in all MP4 players
        "postprocessor_args": ["-c:a", "aac", "-b:a", "192k"],
    }

    # For audio-only downloads: convert to high-quality 320kbps MP3
    if format_id == "bestaudio/best":
        ydl_opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "320",
        }]
        # MP3 output won't be .mp4
        ydl_opts.pop("merge_output_format", None)

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

            with download_lock:
                download_state["progress"] = 100.0
                download_state["status"] = "done"
                download_state["message"] = "Download complete!"
                download_state["file_path"] = final
    except Exception as e:
        with download_lock:
            download_state["status"] = "error"
            download_state["error"] = str(e)
            download_state["message"] = f"Error: {e}"


# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/video", methods=["POST"])
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
                    # bestvideo+bestaudio, prefer m4a (AAC) audio which merges cleanly into MP4
                    {"format_id": "bestvideo+bestaudio[ext=m4a]/bestvideo+bestaudio/best", "label": "Highest Available Quality (Default)"}
                ]

                for res in sorted_res:
                    simplified_formats.append({
                        # Prefer m4a audio; fall back to any bestaudio if m4a not available
                        "format_id": f"bestvideo[height<={res}]+bestaudio[ext=m4a]/bestvideo[height<={res}]+bestaudio/best[height<={res}]",
                        "label": f"{res}p Standard Video"
                    })

                if has_audio or not sorted_res:
                    simplified_formats.append({"format_id": "bestaudio/best", "label": "Audio Only (MP3/M4A)"})

            return render_template("index.html", url=url, formats=simplified_formats, active_tab="video")
        except Exception as e:
            flash(f"Failed to fetch video details: {str(e)}", "error")
            return redirect(url_for("index"))

    elif action == "download":
        format_id = request.form.get("format")
        if not format_id:
            flash("Please select a format to download.", "error")
            return redirect(url_for("index"))

        # Reset and kick off background download
        reset_state()
        temp_name = f"{uuid.uuid4()}.%(ext)s"
        output_template = os.path.join(VIDEO_DOWNLOAD_DIR, temp_name)

        t = threading.Thread(target=run_download, args=(url, format_id, output_template), daemon=True)
        t.start()

        # Return a waiting page that polls progress
        return render_template("index.html", url=url, formats=[], active_tab="video", waiting=True)


@app.route("/api/progress")
def api_progress():
    """Frontend polls this endpoint every second."""
    with download_lock:
        return jsonify({
            "progress": download_state["progress"],
            "status": download_state["status"],
            "message": download_state["message"],
            "error": download_state["error"],
        })


@app.route("/api/download-file")
def api_download_file():
    """Called by the frontend once status is 'done' to fetch the file."""
    with download_lock:
        file_path = download_state["file_path"]
        status = download_state["status"]

    if status != "done" or not file_path or not os.path.exists(file_path):
        return "File not ready", 404

    return send_file(file_path, as_attachment=True)


@app.route("/images", methods=["POST"])
def handle_images():
    query = request.form.get("query")
    count = request.form.get("count", 10, type=int)

    if not query:
        flash("Please provide a search query.", "error")
        return redirect(url_for("index"))

    try:
        download_images(query, save_dir=IMAGE_DOWNLOAD_DIR, max_results=count)
        clean_query = "".join(c if c.isalnum() else "_" for c in query)
        folder = os.path.join(IMAGE_DOWNLOAD_DIR, clean_query)

        if os.path.exists(folder) and os.listdir(folder):
            zip_path = shutil.make_archive(os.path.join(IMAGE_DOWNLOAD_DIR, f"{clean_query}_images"), "zip", folder)
            return send_file(zip_path, as_attachment=True)
        else:
            flash("No images found for that query.", "warning")
            return redirect(url_for("index"))
    except Exception as e:
        flash(f"Error fetching images: {str(e)}", "error")
        return redirect(url_for("index"))


if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("[SUCCESS] Nexus Media Fetcher Server Started!")
    print("[LINK]    CLICK HERE >>> http://127.0.0.1:5000/")
    print("=" * 50 + "\n")
    app.run(debug=True, port=5000, use_reloader=False)
