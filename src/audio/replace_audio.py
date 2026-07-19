import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List
from config import DUCKING_VOLUME, MAX_SPEECH_SPEEDUP
from src.utils.ffmpeg_utils import (
    adjust_audio_speed,
    concat_audio_files,
    create_silence,
    get_media_duration,
    mix_audio_ducking,
    replace_video_audio,
)
from src.utils.logger import setup_logger

logger = setup_logger("audio_replacer")


class AudioReplacementError(Exception):
    """Custom exception for audio replacing failures."""
    pass


class AudioReplacer:
    """
    Stitches individual segment audios together at original timestamps,
    adjusts speed where necessary to avoid overlaps, applies audio ducking
    to keep original background music, and outputs the final dubbed video.
    """

    def __init__(self, output_directory: Path):
        self.output_directory = output_directory
        self.output_directory.mkdir(parents=True, exist_ok=True)

    def replace(
        self,
        video_path: Path,
        original_audio_path: Path,
        segments: List[Dict[str, Any]],
        voice_audio_paths: List[Path]
    ) -> Path:
        """
        Creates the dubbed audio timeline, mixes it with original audio (ducking),
        and replaces the audio track of the original video.
        """
        logger.info(f"Starting audio timeline construction for: {video_path.name}")
        
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")
            
        # Get total video duration
        video_duration = get_media_duration(video_path)
        logger.info(f"Video duration detected: {video_duration:.2f} seconds")

        # Create a temporary directory to store intermediate WAV clips
        temp_dir_obj = tempfile.TemporaryDirectory()
        temp_dir = Path(temp_dir_obj.name)

        try:
            concat_list: List[Path] = []
            current_time = 0.0
            
            for idx, (seg, voice_path) in enumerate(zip(segments, voice_audio_paths)):
                start = seg["start"]
                end = seg["end"]
                target_dur = end - start
                
                # 1. Handle Silent Gap before segment starts
                if start > current_time:
                    gap = start - current_time
                    if gap > 0.005:  # more than 5ms
                        silence_file = temp_dir / f"silence_gap_{idx:04d}.wav"
                        create_silence(gap, silence_file)
                        concat_list.append(silence_file)
                        current_time = start

                # 2. Process segment voice audio (if it exists)
                if voice_path and voice_path.exists():
                    tts_dur = get_media_duration(voice_path)
                    
                    # If synthesized voice is longer than the target video segment duration
                    if tts_dur > target_dur:
                        speed_ratio = tts_dur / target_dur
                        # Cap the maximum speedup ratio to keep speech understandable
                        if speed_ratio > MAX_SPEECH_SPEEDUP:
                            logger.warning(
                                f"Segment {idx} requires speedup of {speed_ratio:.2f}x, which exceeds limit. "
                                f"Capping at {MAX_SPEECH_SPEEDUP}x."
                            )
                            speed_ratio = MAX_SPEECH_SPEEDUP
                            
                        adjusted_file = temp_dir / f"seg_voice_speed_{idx:04d}.wav"
                        adjust_audio_speed(voice_path, adjusted_file, speed_ratio)
                        actual_dur = tts_dur / speed_ratio
                    else:
                        # Convert segment MP3 to 16kHz mono WAV at 1.0x speed
                        adjusted_file = temp_dir / f"seg_voice_normal_{idx:04d}.wav"
                        adjust_audio_speed(voice_path, adjusted_file, 1.0)
                        actual_dur = tts_dur
                        
                    concat_list.append(adjusted_file)
                    current_time += actual_dur
                else:
                    # If segment text is empty/skipped, treat the duration as silence
                    if target_dur > 0:
                        empty_silence = temp_dir / f"silence_empty_{idx:04d}.wav"
                        create_silence(target_dur, empty_silence)
                        concat_list.append(empty_silence)
                        current_time += target_dur

            # 3. Add final silence padding up to the end of the video
            if video_duration > current_time:
                final_gap = video_duration - current_time
                if final_gap > 0.005:
                    final_silence = temp_dir / "silence_final.wav"
                    create_silence(final_gap, final_silence)
                    concat_list.append(final_silence)
                    current_time = video_duration

            # 4. Concatenate all silences and voice WAVs
            raw_dubbed_wav = temp_dir / "raw_dubbed_track.wav"
            logger.info("Stitching audio timeline segments...")
            concat_audio_files(concat_list, raw_dubbed_wav)
            
            # Verify dubbed audio duration
            logger.info(f"Timeline constructed. Total duration: {get_media_duration(raw_dubbed_wav):.2f}s")

            # 5. Mix original background audio (with ducking) and dubbed track
            mixed_dubbed_wav = temp_dir / "mixed_dubbed_track.wav"
            logger.info("Applying background audio ducking and mixing...")
            mix_audio_ducking(
                original_audio=original_audio_path,
                dubbed_audio=raw_dubbed_wav,
                segments=segments,
                output_path=mixed_dubbed_wav,
                ducking_volume=DUCKING_VOLUME
            )

            # 6. Replace audio in original video with our final dubbed-and-ducked track
            output_video = self.output_directory / f"{video_path.stem}_dubbed.mp4"
            logger.info("Muxing final video and audio tracks...")
            replace_video_audio(
                video_path=video_path,
                audio_path=mixed_dubbed_wav,
                output_path=output_video
            )
            
            logger.info(f"Audio replacement completed. Output saved at: {output_video}")
            return output_video

        except Exception as e:
            logger.error(f"Audio replacement pipeline failed: {e}")
            raise AudioReplacementError(f"Failed to replace audio: {e}") from e
        finally:
            # Clean up temporary WAV clips directory
            try:
                temp_dir_obj.cleanup()
            except Exception as e:
                logger.warning(f"Failed to cleanup temp directory: {e}")