import sys
from pathlib import Path
from dotenv import load_dotenv

# Load env variables before doing anything else
load_dotenv()

from src.pipeline import VideoDubbingPipeline


def validate_youtube_url(url: str) -> bool:
    """
    Validates if a given URL is a valid YouTube video URL format.
    """
    url = url.strip()
    if not url:
        print("\n[Error] URL cannot be empty.")
        return False
        
    youtube_domains = [
        "youtube.com/watch",
        "youtu.be/",
        "youtube.com/v/",
        "youtube.com/embed/",
        "youtube.com/shorts/"
    ]
    
    is_valid = any(domain in url for domain in youtube_domains)
    if not is_valid:
        print("\n[Error] Invalid YouTube URL. Must be a valid youtube.com or youtu.be link.")
        return False
        
    return True


def main() -> None:
    """
    Main user interface interactive loop for Automated Video Dubbing.
    """
    print("=" * 80)
    print("                   AUTOMATED VIDEO DUBBING COMMAND CENTER")
    print("=" * 80)
    
    url = input("\nEnter YouTube Video URL : ").strip()
    
    if not validate_youtube_url(url):
        sys.exit(1)
        
    try:
        pipeline = VideoDubbingPipeline()
        pipeline.run(url)
    except KeyboardInterrupt:
        print("\n[Warning] Process aborted by user.")
        sys.exit(130)
    except Exception as e:
        print(f"\n[Error] Critical system error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()