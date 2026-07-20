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
    OUTPUT_DIR,
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

    def __init__(
        self,
        whisper_model_name: Optional[str] = None,
        tts_voice: Optional[str] = None,
        target_lang: Optional[str] = None
    ):
        # Configuration parameters loaded with Env priority
        self.whisper_model_name = whisper_model_name or os.getenv("WHISPER_MODEL", WHISPER_MODEL)
        self.tts_voice = tts_voice or os.getenv("EDGE_TTS_VOICE", EDGE_TTS_VOICE)
        self.target_lang = target_lang or os.getenv("OUTPUT_LANGUAGE", "en")
        
        # Instantiate child components
        self.downloader = YouTubeDownloader(VIDEO_DIR)
        self.extractor = AudioExtractor(AUDIO_DIR)
        self.transcriber = WhisperTranscriber(self.whisper_model_name, TRANSCRIPT_DIR)
        self.translator = VideoTranslator(TRANSLATED_TEXT_DIR)
        self.tts_engine = EdgeTTSEngine(ENGLISH_AUDIO_DIR, self.tts_voice)
        self.replacer = AudioReplacer(DUBBED_VIDEO_DIR)
        self.timer = StepTimer()

    def run(
        self,
        url: str,
        whisper_model: Optional[str] = None,
        voice: Optional[str] = None,
        target_lang: Optional[str] = None,
        progress_callback = None
    ) -> Optional[Path]:
        """
        Executes the entire automated video dubbing workflow.
        """
        print_banner()
        logger.info("Initializing Video Dubbing Pipeline...")
        
        # Dynamic configuration overrides
        if whisper_model and whisper_model != self.whisper_model_name:
            self.whisper_model_name = whisper_model
            self.transcriber = WhisperTranscriber(self.whisper_model_name, TRANSCRIPT_DIR)
        if voice and voice != self.tts_voice:
            self.tts_voice = voice
            self.tts_engine = EdgeTTSEngine(ENGLISH_AUDIO_DIR, self.tts_voice)
        if target_lang and target_lang != self.target_lang:
            self.target_lang = target_lang

        video_path: Optional[Path] = None
        audio_path: Optional[Path] = None
        transcript_data = None
        translated_segments = None
        voice_paths = []
        final_video_path: Optional[Path] = None
        srt_path: Optional[Path] = None
        
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
            if progress_callback:
                progress_callback(5, "Downloading YouTube Video...")
            with self.timer.time_step("Download"):
                video_path = self.downloader.download(url)
            logger.info(f"Video downloaded to: {video_path.name}")
            if progress_callback:
                progress_callback(20, f"Video downloaded: {video_path.name}")

            # Get video info
            video_duration = get_media_duration_ref_local(video_path)

            # ----------------------------------------------------
            # STEP 2: Extract Audio
            # ----------------------------------------------------
            print_step_banner(2, "Extracting Original Audio Track")
            if progress_callback:
                progress_callback(25, "Extracting original audio track...")
            with self.timer.time_step("Audio Extraction"):
                audio_path = self.extractor.extract(video_path)
            logger.info(f"Audio extracted to: {audio_path.name}")
            if progress_callback:
                progress_callback(35, "Audio extraction completed.")

            # ----------------------------------------------------
            # STEP 3: Transcribe Speech-to-Text
            # ----------------------------------------------------
            print_step_banner(3, "Transcribing speech using Whisper")
            if progress_callback:
                progress_callback(40, f"Transcribing speech using Whisper ({self.whisper_model_name})...")
            with self.timer.time_step("Transcription"):
                transcript_data = self.transcriber.transcribe(audio_path)
            detected_language = transcript_data["language"]
            logger.info(f"Transcription complete. Language: '{detected_language}'")
            if progress_callback:
                progress_callback(55, f"Speech transcribed. Detected language: {detected_language}")

            # ----------------------------------------------------
            # STEP 4: Translate Transcript & Generate SRT Subtitles
            # ----------------------------------------------------
            print_step_banner(4, f"Translating segments to {self.target_lang}")
            if progress_callback:
                progress_callback(60, f"Translating segments to {self.target_lang}...")
            with self.timer.time_step("Translation"):
                translated_segments = self.translator.translate_segments(
                    segments=transcript_data["segments"],
                    source_lang=detected_language,
                    target_lang=self.target_lang
                )
            
            # Generate SRT Subtitle file automatically
            srt_path = SUBTITLE_DIR / "video.srt"
            generate_srt(translated_segments, srt_path)
            logger.info(f"English Subtitles generated successfully: {srt_path.name}")
            if progress_callback:
                progress_callback(70, "Translation completed & subtitles generated.")

            # ----------------------------------------------------
            # STEP 5: Generate TTS Voice
            # ----------------------------------------------------
            print_step_banner(5, f"Synthesizing {self.target_lang} voice clips")
            if progress_callback:
                progress_callback(75, f"Synthesizing speech segments ({self.tts_voice})...")
            with self.timer.time_step("TTS Generation"):
                voice_paths = self.tts_engine.generate_dubbed_segments(
                    segments=translated_segments
                )
            logger.info("Voice synthesis completed for all segments.")
            if progress_callback:
                progress_callback(85, "Voice synthesis completed.")

            # ----------------------------------------------------
            # STEP 6: Replace Audio & Final Dub Muxing
            # ----------------------------------------------------
            print_step_banner(6, "Generating Final Dubbed Video")
            if progress_callback:
                progress_callback(90, "Muxing final video and audio...")
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
            if progress_callback:
                progress_callback(100, "Dubbing pipeline completed successfully!")
            
            return final_video_path

        except KeyboardInterrupt:
            error_msg = "Pipeline execution was cancelled by user."
            logger.warning(error_msg)
            print("\nExecution Interrupted by User.")
            if progress_callback:
                progress_callback(100, "Execution cancelled by user.")
            return None
            
        except Exception as e:
            status = "FAILED"
            error_msg = str(e)
            logger.exception(f"Pipeline crashed on step: {e}")
            print(f"\nPipeline execution failed: {e}")
            if progress_callback:
                progress_callback(100, f"Error: {e}")
            return None
            
        finally:
            pipeline_end_time = time.perf_counter()
            total_elapsed = pipeline_end_time - pipeline_start_time
            
            # Write final JSON execution report
            report_path = OUTPUT_DIR / "report.json"
            
            generated_files = []
            if video_path and video_path.exists():
                generated_files.append(str(video_path.resolve()))
            if audio_path and audio_path.exists():
                generated_files.append(str(audio_path.resolve()))
            if final_video_path and final_video_path.exists():
                generated_files.append(str(final_video_path.resolve()))
            if srt_path and srt_path.exists():
                generated_files.append(str(srt_path.resolve()))
                
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