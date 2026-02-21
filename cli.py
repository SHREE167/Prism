import argparse
import sys
from main import download_images
from videodownloader import download_video

def main():
    parser = argparse.ArgumentParser(
        description="Media Fetcher CLI - Download Images from Google or Videos from YouTube",
        epilog="Examples:\n  python cli.py images \"cute dogs\"\n  python cli.py video https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Choose a media type to fetch")
    
    # --- Image Fetcher Parser ---
    image_parser = subparsers.add_parser("images", help="Download images using SerpApi")
    image_parser.add_argument("query", type=str, help="Search query (e.g., 'funny cats')")
    image_parser.add_argument("-n", "--number", type=int, default=10, help="Number of images to fetch (default: 10)")
    image_parser.add_argument("-d", "--dir", type=str, default="images", help="Output directory (default: 'images')")
    
    # --- Video Fetcher Parser ---
    video_parser = subparsers.add_parser("video", help="Download a video using yt-dlp")
    video_parser.add_argument("url", type=str, help="URL of the video to download")
    video_parser.add_argument("-a", "--audio", action="store_true", help="Download audio only (extracts mp3)")
    video_parser.add_argument("-d", "--dir", type=str, default="videos", help="Output directory (default: 'videos')")
    
    args = parser.parse_args()

    if args.command == "images":
        print(f"Starting Image Fetcher for: '{args.query}'")
        download_images(args.query, save_dir=args.dir, max_results=args.number)
        
    elif args.command == "video":
        print(f"Starting Video Fetcher for: '{args.url}'")
        download_video(args.url, output_dir=args.dir, audio_only=args.audio)
        
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
