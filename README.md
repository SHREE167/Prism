# Prism Media Fetcher 🌈

Prism is a sleek, modern web application built with Python and Flask that allows you to easily download videos from YouTube in various resolutions and batch download images from Google Search. It features a secure authentication system powered by Supabase and a beautiful UI with Dark/Light mode support.

## 🚀 Features

- **🎥 YouTube Video Downloader**: Download YouTube videos in the highest available quality, specific resolutions, or audio-only (MP3). Automatically merges video and audio streams.
- **🖼️ Image Search & Batch Downloader**: Search for any query and instantly fetch up to 50 images from Google (via SerpAPI), bundled conveniently into a downloadable ZIP file.
- **🔐 Secure Authentication**: User sign-up and login handled safely through Supabase Auth.
- **⚡ Asynchronous Downloads**: Downloads run seamlessly in the background with real-time progress tracking in the UI.
- **🌗 Dark / Light Mode**: Beautiful UI with a toggleable dark and light theme, complete with micro-animations.

## 🛠️ Tech Stack

- **Backend**: Python, Flask, Gunicorn
- **Frontend**: HTML5, Vanilla CSS, JavaScript
- **Database/Auth**: [Supabase](https://supabase.com/)
- **Video Processing**: [yt-dlp](https://github.com/yt-dlp/yt-dlp) & [FFmpeg](https://ffmpeg.org/)
- **Image Search API**: [SerpAPI](https://serpapi.com/)

---

## 💻 Installation & Setup

### 1. Prerequisites
- **Python 3.10+** installed.
- **FFmpeg** installed and added to your system's `PATH`. (Alternatively, you can specify its location in the `.env` file).

### 2. Clone the Repository
```bash
git clone https://github.com/SHREE167/Prism.git
cd Prism
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Create a `.env` file in the root directory of the project and add the following keys:

```env
# Supabase Configuration (Get these from your Supabase Dashboard)
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_KEY=your-anon-public-key

# Flask Security (Create a strong, random hex string)
FLASK_SECRET_KEY=your-super-secret-flask-key

# SerpAPI Key for Image Search (Get this from serpapi.com)
API_KEY=your-serpapi-key

# Optional: Path to FFmpeg executable if it's not in your system PATH
# FFMPEG_PATH=C:\path\to\ffmpeg.exe
```

> **Note on Supabase Auth:** By default, new Supabase projects require Email Confirmation. If you want to disable this for testing, go to **Authentication > Providers > Email** in your Supabase dashboard and turn off "Confirm email".

### 5. Run the Application

**For Local Development:**
```bash
python app.py
```
The app will be available at `http://127.0.0.1:5000/`.

**For Production:**
```bash
gunicorn app:app --workers 1 --timeout 120
```

---

## 📖 Usage

1. **Sign Up / Log In**: Create an account to access the downloader tools.
2. **Video Fetcher**: Paste a YouTube URL, click "Analyze Formats", select your desired quality, and click "Download". The video will automatically download to your machine once processed.
3. **Image Fetcher**: Enter a search term (e.g., "cyberpunk cityscapes"), set the number of images to fetch, and click "Fetch Images". A ZIP file containing the images will be downloaded.

## 🤝 Contributing
Contributions, issues, and feature requests are welcome! Feel free to check the [issues page](https://github.com/SHREE167/Prism/issues).

## 📝 License
This project is open-source and available for educational and personal use.
