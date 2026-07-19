import os
import time
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

from config import (
    AUDIO_DIR,
    DUBBED_VIDEO_DIR,
    EDGE_TTS_VOICE,
    ENGLISH_AUDIO_DIR,
    LOG_DIR,
    SUBTITLE_DIR,
    TRANSCRIPT_DIR,
    TRANSLATED_TEXT_DIR,
    VIDEO_DIR,
    WHISPER_MODEL,
)
from src.downloader.youtube_downloader import YouTubeDownloader
from src.audio.extract_audio import AudioExtractor
from src.transcription.whisper_transcriber import WhisperTranscriber
from src.translation.translator import VideoTranslator
from src.tts.edge_tts_engine import EdgeTTSEngine
from src.audio.replace_audio import AudioReplacer
from src.utils.timer import StepTimer
from src.utils.logger import setup_logger
from src.utils.helpers import (
    generate_srt,
    print_banner,
    print_step_banner,
    write_execution_report,
)

logger = setup_logger("pipeline")


class VideoDubbingPipeline:
    """
    End-to-End Orchestrator for the Automated Video Dubbing System.
    Manages state, execution steps, logging, subtitle generation, and reporting.
    """

    def __init__(self):
        # Configuration parameters loaded with Env priority
        self.whisper_model_name = os.getenv("WHISPER_MODEL", WHISPER_MODEL)
        self.tts_voice = os.getenv("EDGE_TTS_VOICE", EDGE_TTS_VOICE)
        self.target_lang = os.getenv("OUTPUT_LANGUAGE", "en")
        
        # Instantiate child components
        self.downloader = YouTubeDownloader(VIDEO_DIR)
        self.extractor = AudioExtractor(AUDIO_DIR)
        self.transcriber = WhisperTranscriber(self.whisper_model_name, TRANSCRIPT_DIR)
        self.translator = VideoTranslator(TRANSLATED_TEXT_DIR)
        self.tts_engine = EdgeTTSEngine(ENGLISH_AUDIO_DIR, self.tts_voice)
        self.replacer = AudioReplacer(DUBBED_VIDEO_DIR)
        self.timer = StepTimer()

    def run(self, url: str) -> Optional[Path]:
        """
        Executes the entire automated video dubbing workflow.
        """
        print_banner()
        logger.info("Initializing Video Dubbing Pipeline...")
        
        video_path: Optional[Path] = None
        audio_path: Optional[Path] = None
        transcript_data = None
        translated_segments = None
        voice_paths = []
        final_video_path: Optional[Path] = None
        
        video_duration = 0.0
        detected_language = "unknown"
        status = "FAILED"
        error_msg = ""
        
        pipeline_start_time = time.perf_counter()
        
        try:
            # ----------------------------------------------------
            # STEP 1: Download Video
            # ----------------------------------------------------
            print_step_banner(1, "Downloading YouTube Video")
            with self.timer.time_step("Download"):
                video_path = self.downloader.download(url)
            logger.info(f"Video downloaded to: {video_path.name}")

            # Get video info
            video_duration = get_media_duration_ref_local(video_path)

            # ----------------------------------------------------
            # STEP 2: Extract Audio
            # ----------------------------------------------------
            print_step_banner(2, "Extracting Original Audio Track")
            with self.timer.time_step("Audio Extraction"):
                audio_path = self.extractor.extract(video_path)
            logger.info(f"Audio extracted to: {audio_path.name}")

            # ----------------------------------------------------
            # STEP 3: Transcribe Speech-to-Text
            # ----------------------------------------------------
            print_step_banner(3, "Transcribing speech using Whisper")
            with self.timer.time_step("Transcription"):
                transcript_data = self.transcriber.transcribe(audio_path)
            detected_language = transcript_data["language"]
            logger.info(f"Transcription complete. Language: '{detected_language}'")

            # ----------------------------------------------------
            # STEP 4: Translate Transcript & Generate SRT Subtitles
            # ----------------------------------------------------
            print_step_banner(4, "Translating segments to English")
            with self.timer.time_step("Translation"):
                translated_segments = self.translator.translate_segments(
                    segments=transcript_data["segments"],
                    source_lang=detected_language,
                    target_lang=self.target_lang
                )
            
            # Generate SRT Subtitle file automatically
            srt_path = SUBTITLE_DIR / f"{video_path.stem}_english.srt"
            generate_srt(translated_segments, srt_path)
            logger.info(f"English Subtitles generated successfully: {srt_path.name}")

            # ----------------------------------------------------
            # STEP 5: Generate English TTS Voice
            # ----------------------------------------------------
            print_step_banner(5, "Synthesizing English voice clips")
            with self.timer.time_step("TTS Generation"):
                voice_paths = self.tts_engine.generate_dubbed_segments(
                    segments=translated_segments
                )
            logger.info("Voice synthesis completed for all segments.")

            # ----------------------------------------------------
            # STEP 6: Replace Audio & Final Dub Muxing
            # ----------------------------------------------------
            print_step_banner(6, "Generating Final Dubbed Video")
            with self.timer.time_step("Audio Replacement & Muxing"):
                final_video_path = self.replacer.replace(
                    video_path=video_path,
                    original_audio_path=audio_path,
                    segments=translated_segments,
                    voice_audio_paths=voice_paths
                )
                
            status = "SUCCESS"
            logger.info("End-to-End Dubbing Pipeline successfully completed!")
            print("\n" + "=" * 80)
            print(f"DUBBING PIPELINE FINISHED SUCCESSFULLY!")
            print(f"Final Video : {final_video_path}")
            print(f"Subtitles   : {srt_path}")
            print("=" * 80)
            
            return final_video_path

        except KeyboardInterrupt:
            error_msg = "Pipeline execution was cancelled by user."
            logger.warning(error_msg)
            print("\nExecution Interrupted by User.")
            return None
            
        except Exception as e:
            status = "FAILED"
            error_msg = str(e)
            logger.exception(f"Pipeline crashed on step: {e}")
            print(f"\nPipeline execution failed: {e}")
            return None
            
        finally:
            pipeline_end_time = time.perf_counter()
            total_elapsed = pipeline_end_time - pipeline_start_time
            
            # Write final JSON execution report
            report_name = f"{video_path.stem if video_path else 'unknown'}_report.json"
            report_path = DUBBED_VIDEO_DIR / report_name
            
            generated_files = []
            if video_path and video_path.exists():
                generated_files.append(str(video_path.resolve()))
            if audio_path and audio_path.exists():
                generated_files.append(str(audio_path.resolve()))
            if final_video_path and final_video_path.exists():
                generated_files.append(str(final_video_path.resolve()))
                
            # Log summary to console
            print("\n" + "=" * 80)
            print("EXECUTION TIME METRICS SUMMARY")
            print("=" * 80)
            for step, dur in self.timer.steps:
                print(f" - {step:<30} : {self.timer.format_duration(dur)}")
            print("-" * 80)
            print(f" - Total Time                       : {self.timer.format_duration(total_elapsed)}")
            print("=" * 80)

            write_execution_report(
                output_path=report_path,
                video_name=video_path.name if video_path else "unknown",
                duration=video_duration,
                input_language=detected_language,
                output_language=self.target_lang,
                processing_time=total_elapsed,
                generated_files=generated_files,
                status=status,
                whisper_model=self.whisper_model_name,
                voice_model=self.tts_voice,
                error_reason=error_msg
            )
            logger.info(f"Execution report generated and saved at: {report_path.name}")


def get_media_duration_ref_local(path: Path) -> float:
    """Helper to extract duration locally, wraps ffmpeg_utils query."""
    from src.utils.ffmpeg_utils import get_media_duration
    try:
        return get_media_duration(path)
    except Exception:
        return 0.0