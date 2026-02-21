# main.py

import os
import requests
from serpapi import GoogleSearch
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ✅ Your API Key loaded securely
API_KEY = os.getenv("API_KEY")

def search_images(query, max_results=10):
    if not API_KEY:
        print("❌ Error: API_KEY not found. Please add it to the .env file.")
        return []

    print(f"\nSearching images for: {query}")
    params = {
        "engine": "google",
        "q": query,
        "tbm": "isch",
        "api_key": API_KEY,
    }

    try:
        search = GoogleSearch(params)
        results = search.get_dict()
        if "error" in results:
            print(f"API Error: {results['error']}")
            return []
            
        images = results.get("images_results", [])
        return images[:max_results]
    except Exception as e:
        print(f"Failed to search for {query}: {e}")
        return []

def download_images(query, save_dir="images", max_results=10):
    images = search_images(query, max_results)
    if not images:
        print(f"No images found or retrieved for {query}")
        return

    # Clean the query for the folder name
    clean_query = "".join(c if c.isalnum() else "_" for c in query)
    folder = os.path.join(save_dir, clean_query)
    os.makedirs(folder, exist_ok=True)

    downloaded_count = 0
    for i, image in enumerate(images):
        try:
            img_url = image.get("original")
            if not img_url:
                continue
                
            response = requests.get(img_url, timeout=10)
            response.raise_for_status() # Check for HTTP errors
            
            # Simple extension extraction, defaulting to .jpg
            ext = img_url.split('.')[-1]
            if len(ext) > 4 or not ext.isalnum():
                ext = "jpg"
                
            file_path = os.path.join(folder, f"{i+1}.{ext}")
            with open(file_path, "wb") as f:
                f.write(response.content)
            print(f"Saved: {file_path}")
            downloaded_count += 1
        except Exception as e:
            print(f"Failed to download {img_url}: {e}")

    print(f"\nSuccessfully downloaded {downloaded_count} images for '{query}'.")

if __name__ == "__main__":
    # 🔍 Search terms
    queries = [
        "cat",
    ]
    # 🚀 Run through all queries
    for query in queries:
        download_images(query)

    input("\nAll done! Press Enter to exit...")
