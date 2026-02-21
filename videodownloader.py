import os
import yt_dlp

def download_video(url, output_dir="videos", audio_only=False):
    """
    Downloads a video from YouTube (or other supported sites) using yt-dlp.
    """
    print(f"\nDownloading video from: {url}")
    os.makedirs(output_dir, exist_ok=True)
    
    # FFMPEG built-in path
    FFMPEG_EXE_PATH = r"C:\Users\Shree\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin\ffmpeg.exe"

    # Base options
    ydl_opts = {
        'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
        'quiet': False,
        'no_warnings': True,
        'ffmpeg_location': FFMPEG_EXE_PATH,
    }

    if audio_only:
        print("Audio-only extraction selected.")
        ydl_opts.update({
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        })
    else:
        # Download best video and best audio combined, or best combined format
        ydl_opts.update({
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        })

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        print("Download completed successfully!")
    except Exception as e:
        print(f"Failed to download video: {e}")

if __name__ == "__main__":
    # Test block
    test_url = input("Enter a YouTube URL to test download: ").strip()
    if test_url:
        download_video(test_url)
