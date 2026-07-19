import logging
from pathlib import Path
from typing import Any, Dict, Optional
import yt_dlp
from config import YTDLP_FRAGMENT_RETRIES, YTDLP_RETRIES
from src.utils.logger import setup_logger

logger = setup_logger("youtube_downloader")


class DownloadError(Exception):
    """Custom exception for YouTube downloader failures."""
    pass


class YouTubeDownloader:
    """
    Downloads YouTube videos in the best available quality, merges audio and video,
    supports download resume, retries, and outputs download metrics.
    """

    def __init__(self, output_directory: Path):
        self.output_directory = output_directory
        self.output_directory.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def progress_hook(data: Dict[str, Any]) -> None:
        """
        Custom progress hook to report percentages, download speed, and ETA.
        """
        status = data.get("status")
        
        if status == "downloading":
            downloaded = data.get("downloaded_bytes", 0)
            total = (
                data.get("total_bytes")
                or data.get("total_bytes_estimate")
                or 0
            )
            speed = data.get("speed", 0) or 0  # bytes/second
            eta = data.get("eta", 0) or 0      # seconds
            
            percent_str = "0.00%"
            if total > 0:
                percent = downloaded * 100 / total
                percent_str = f"{percent:.2f}%"
                
            # Format speed
            if speed > 1024 * 1024:
                speed_str = f"{speed / (1024 * 1024):.2f} MB/s"
            elif speed > 1024:
                speed_str = f"{speed / 1024:.2f} KB/s"
            else:
                speed_str = f"{speed:.0f} B/s"
                
            # Format ETA
            if eta > 60:
                m, s = divmod(eta, 60)
                eta_str = f"{m}m {s}s"
            else:
                eta_str = f"{eta}s"
                
            print(
                f"\rDownloading : {percent_str:<7} | Speed: {speed_str:<10} | ETA: {eta_str:<8}",
                end="",
                flush=True,
            )
            
        elif status == "finished":
            print("\nDownload finished. Processing and merging files...")

    def download(self, url: str) -> Path:
        """
        Downloads a video from a YouTube URL and returns the local Path to it.
        """
        logger.info(f"Initiating download for: {url}")
        
        # Configure yt-dlp options
        options = {
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "merge_output_format": "mp4",
            "outtmpl": str(self.output_directory / "%(title)s.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [self.progress_hook],
            "retries": YTDLP_RETRIES,
            "fragment_retries": YTDLP_FRAGMENT_RETRIES,
            "continuedl": True,  # Allow resuming downloads
        }

        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=True)
                if info is None:
                    raise DownloadError("Failed to extract video information.")
                    
                filename = ydl.prepare_filename(info)
                video_path = Path(filename)
                
                # Check if file has suffix mp4 (sometimes merge changes extension to mp4)
                if video_path.suffix != ".mp4":
                    mp4_path = video_path.with_suffix(".mp4")
                    if mp4_path.exists():
                        video_path = mp4_path
                
                if not video_path.exists():
                    raise DownloadError(f"Expected output file not found at: {video_path}")
                
                logger.info(f"Download successful. Saved to: {video_path}")
                print(f"\nTitle      : {info.get('title')}")
                print(f"Duration   : {info.get('duration')} seconds")
                print(f"Uploader   : {info.get('uploader')}")
                print(f"Resolution : {info.get('resolution')}")
                
                return video_path
                
        except Exception as e:
            logger.error(f"Failed to download video: {e}")
            raise DownloadError(f"Download process failed: {e}") from e