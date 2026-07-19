import logging
from pathlib import Path
from typing import Any, Dict
import whisper
from src.utils.logger import setup_logger

logger = setup_logger("whisper_transcriber")


class TranscriptionError(Exception):
    """Custom exception for transcription failures."""
    pass


class WhisperTranscriber:
    """
    Transcribes audio into text and segments using OpenAI Whisper.
    Auto-detects input language and caches the model to avoid reloading.
    """

    def __init__(self, model_name: str, transcript_directory: Path):
        self.transcript_directory = transcript_directory
        self.transcript_directory.mkdir(parents=True, exist_ok=True)
        self.model_name = model_name
        self.model = None

    def _load_model(self) -> whisper.Whisper:
        """
        Loads the whisper model if it hasn't been loaded already.
        """
        if self.model is None:
            logger.info(f"Loading Whisper model: {self.model_name}")
            try:
                self.model = whisper.load_model(self.model_name)
                logger.info("Whisper model loaded successfully.")
            except Exception as e:
                logger.critical(f"Failed to load Whisper model: {e}")
                raise TranscriptionError(f"Model load failure: {e}") from e
        return self.model

    def transcribe(self, audio_path: Path) -> Dict[str, Any]:
        """
        Transcribes the given audio file, auto-detects language,
        saves the full transcript text, and returns segment details.
        """
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file for transcription not found: {audio_path}")
            
        model = self._load_model()
        logger.info(f"Transcribing audio file: {audio_path.name}")
        
        try:
            # Run transcription (fp16=False is safer/default on CPU to prevent warnings)
            result = model.transcribe(str(audio_path), fp16=False)
            
            transcript_text = result.get("text", "").strip()
            language = result.get("language", "unknown")
            segments = result.get("segments", [])
            
            # Save the full transcript text
            transcript_file = self.transcript_directory / f"{audio_path.stem}.txt"
            transcript_file.write_text(transcript_text, encoding="utf-8")
            
            logger.info(f"Transcription complete. Language: '{language}'. Saved: {transcript_file.name}")
            
            return {
                "language": language,
                "text": transcript_text,
                "transcript_file": transcript_file,
                "segments": segments
            }
            
        except Exception as e:
            logger.error(f"Whisper transcription failed: {e}")
            raise TranscriptionError(f"Transcription failed: {e}") from e