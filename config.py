import os
from pathlib import Path

# ==========================================================
# BASE DIRECTORIES
# ==========================================================
BASE_DIR = Path(__file__).resolve().parent

INPUT_DIR = BASE_DIR / "input"
VIDEO_DIR = INPUT_DIR / "videos"
AUDIO_DIR = INPUT_DIR / "audio"
TRANSCRIPT_DIR = INPUT_DIR / "transcript"

OUTPUT_DIR = BASE_DIR / "output"
DUBBED_VIDEO_DIR = OUTPUT_DIR / "dubbed_videos"
ENGLISH_AUDIO_DIR = OUTPUT_DIR / "english_audio"
TRANSLATED_TEXT_DIR = OUTPUT_DIR / "translated_text"
SUBTITLE_DIR = OUTPUT_DIR / "subtitles"
LOG_DIR = OUTPUT_DIR / "logs"

# Ensure all directories exist automatically
DIRECTORIES = [
    INPUT_DIR,
    VIDEO_DIR,
    AUDIO_DIR,
    TRANSCRIPT_DIR,
    OUTPUT_DIR,
    DUBBED_VIDEO_DIR,
    ENGLISH_AUDIO_DIR,
    TRANSLATED_TEXT_DIR,
    SUBTITLE_DIR,
    LOG_DIR,
]

for directory in DIRECTORIES:
    directory.mkdir(parents=True, exist_ok=True)

# ==========================================================
# AUDIO PROCESSING SETTINGS
# ==========================================================
SAMPLE_RATE = 16000
CHANNELS = 1
AUDIO_CODEC = "pcm_s16le"
AUDIO_FORMAT = "wav"

# Audio Ducking Settings
DUCKING_VOLUME = 0.15          # Volume level of original audio during ducking (15%)
DEFAULT_SPEECH_VOLUME = 1.0     # Volume level of dubbed speech (100%)
MAX_SPEECH_SPEEDUP = 2.0        # Max speedup ratio allowed using ffmpeg's atempo

# ==========================================================
# VIDEO SETTINGS
# ==========================================================
VIDEO_FORMAT = "mp4"

# ==========================================================
# TRANSLATION & SPEECH SETTINGS
# ==========================================================
# Whisper Model Configuration
WHISPER_MODEL = "base"

# Edge-TTS Engine Configuration
# Available voices: en-US-GuyNeural, en-US-AriaNeural, en-GB-SoniaNeural, etc.
EDGE_TTS_VOICE = "en-US-GuyNeural"
DEFAULT_TARGET_LANGUAGE = "en"

# ==========================================================
# LOGGING & LOG EXECUTION CONFIG
# ==========================================================
LOG_LEVEL = "INFO"
LOG_FILE_PATH = LOG_DIR / "dubbing_pipeline.log"

# yt-dlp Configuration
YTDLP_RETRIES = 5
YTDLP_FRAGMENT_RETRIES = 10