import subprocess
from pathlib import Path
from config import AUDIO_CODEC, CHANNELS, SAMPLE_RATE
from src.utils.logger import setup_logger

logger = setup_logger("audio_extractor")


class AudioExtractionError(Exception):
    """Custom exception for audio extraction failures."""
    pass


class AudioExtractor:
    """
    Extracts the audio track from a video file and converts it into
    a mono, 16kHz, PCM WAV file.
    """

    def __init__(self, output_directory: Path):
        self.output_directory = output_directory
        self.output_directory.mkdir(parents=True, exist_ok=True)

    def extract(self, video_path: Path) -> Path:
        """
        Extracts mono 16kHz WAV audio from a video.
        """
        logger.info(f"Extracting audio from: {video_path.name}")
        
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")
            
        output_audio = self.output_directory / f"{video_path.stem}.wav"
        
        command = [
            "ffmpeg",
            "-y",
            "-i", str(video_path),
            "-vn",                       # Disable video stream
            "-acodec", AUDIO_CODEC,      # Set PCM 16-bit codec
            "-ar", str(SAMPLE_RATE),     # Set sample rate (16000)
            "-ac", str(CHANNELS),        # Set channels (1 = mono)
            str(output_audio)
        ]
        
        try:
            subprocess.run(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                check=True
            )
            logger.info(f"Audio extracted successfully: {output_audio.name}")
            return output_audio
        except subprocess.CalledProcessError as e:
            stderr_msg = e.stderr.decode("utf-8") if e.stderr else "Unknown error"
            logger.error(f"FFmpeg extraction failed: {stderr_msg}")
            raise AudioExtractionError(f"FFmpeg audio extraction failed: {stderr_msg}") from e
        except Exception as e:
            logger.error(f"Unexpected error during audio extraction: {e}")
            raise AudioExtractionError(f"Extraction failed: {e}") from e