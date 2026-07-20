import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List
import ffmpeg
from src.utils.logger import setup_logger

logger = setup_logger("ffmpeg_utils")


class FFmpegError(Exception):
    """Custom exception for FFmpeg failures."""
    pass


def get_media_duration(file_path: Path) -> float:
    """
    Retrieves the duration of a video or audio file in seconds.
    """
    try:
        if not file_path.exists():
            raise FileNotFoundError(f"Media file not found at: {file_path}")
        
        probe = ffmpeg.probe(str(file_path))
        format_info = probe.get("format", {})
        duration = format_info.get("duration")
        if duration is not None:
            return float(duration)
        
        # Fallback to streams
        for stream in probe.get("streams", []):
            if "duration" in stream:
                return float(stream["duration"])
                
        raise FFmpegError("Duration field not found in metadata.")
    except Exception as e:
        logger.error(f"Failed to get duration for {file_path.name}: {e}")
        raise FFmpegError(f"Probing failed: {e}") from e


def create_silence(duration: float, output_path: Path) -> Path:
    """
    Generates a silent mono 16kHz WAV file of a specific duration.
    """
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Construct ffmpeg command using ffmpeg-python
        stream = ffmpeg.input("anullsrc=r=16000:cl=mono", f="lavfi")
        stream = ffmpeg.output(stream, str(output_path), t=duration, acodec="pcm_s16le")
        ffmpeg.run(stream, overwrite_output=True, capture_stdout=True, capture_stderr=True)
        return output_path
    except ffmpeg.Error as e:
        stderr_msg = e.stderr.decode("utf-8") if e.stderr else "No stderr details"
        logger.error(f"FFmpeg silence creation failed: {stderr_msg}")
        raise FFmpegError(f"Silence creation failed: {stderr_msg}") from e


def adjust_audio_speed(input_path: Path, output_path: Path, speed_ratio: float) -> Path:
    """
    Adjusts the speed of an audio file using the 'atempo' filter.
    Handles speeds outside the standard [0.5, 2.0] range by chaining atempo filters.
    """
    try:
        if not input_path.exists():
            raise FileNotFoundError(f"Input audio for speed adjustment not found: {input_path}")
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Build speed filters
        filters = []
        temp_ratio = speed_ratio
        
        # atempo filter only supports 0.5 to 2.0. So chain them if necessary.
        while temp_ratio > 2.0:
            filters.append("atempo=2.0")
            temp_ratio /= 2.0
        while temp_ratio < 0.5:
            filters.append("atempo=0.5")
            temp_ratio /= 0.5
            
        filters.append(f"atempo={temp_ratio:.4f}")
        filter_str = ",".join(filters)
        
        # To avoid syntax issues in complex filter string representation, let's invoke subprocess for speed adjustment
        cmd = [
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-filter:a", filter_str,
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            str(output_path)
        ]
        
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
        return output_path
    except subprocess.CalledProcessError as e:
        stderr_msg = e.stderr.decode("utf-8") if e.stderr else "No stderr details"
        logger.error(f"Audio speed adjustment failed: {stderr_msg}")
        raise FFmpegError(f"Speed adjustment failed: {stderr_msg}") from e


def process_audio_segment(
    input_path: Path,
    output_path: Path,
    target_duration: float,
    max_speedup: float = 2.0
) -> Path:
    """
    Processes a single audio segment to match a target duration.
    1. Computes the speed ratio: tts_duration / target_duration.
    2. If tts_duration > target_duration:
       - Speeds up the audio using 'atempo' filter, capping at max_speedup.
       - Trims the resulting audio to exactly target_duration.
    3. If tts_duration <= target_duration:
       - Keeps the audio at 1.0x speed.
       - Pads the audio with silence at the end to match exactly target_duration.
    Ensures output is 16kHz mono WAV format.
    """
    if not input_path.exists():
        raise FileNotFoundError(f"Input audio for processing not found: {input_path}")
        
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tts_dur = get_media_duration(input_path)
    
    try:
        if tts_dur > target_duration:
            speed_ratio = tts_dur / target_duration
            if speed_ratio > max_speedup:
                logger.warning(
                    f"Segment requires speedup of {speed_ratio:.2f}x, which exceeds limit. "
                    f"Capping at {max_speedup}x and trimming."
                )
                speed_ratio = max_speedup
            
            # Build speed filters
            filters = []
            temp_ratio = speed_ratio
            while temp_ratio > 2.0:
                filters.append("atempo=2.0")
                temp_ratio /= 2.0
            while temp_ratio < 0.5:
                filters.append("atempo=0.5")
                temp_ratio /= 0.5
            filters.append(f"atempo={temp_ratio:.4f}")
            filter_str = ",".join(filters)
            
            # Speed up and trim to target_duration
            cmd = [
                "ffmpeg", "-y",
                "-i", str(input_path),
                "-filter:a", filter_str,
                "-t", f"{target_duration:.3f}",
                "-acodec", "pcm_s16le",
                "-ar", "16000",
                "-ac", "1",
                str(output_path)
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
        else:
            # tts_dur <= target_duration
            # Convert input to temporary WAV at 1.0x speed
            temp_wav = output_path.parent / f"temp_{output_path.name}"
            cmd_convert = [
                "ffmpeg", "-y",
                "-i", str(input_path),
                "-acodec", "pcm_s16le",
                "-ar", "16000",
                "-ac", "1",
                str(temp_wav)
            ]
            subprocess.run(cmd_convert, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
            
            pad_dur = target_duration - tts_dur
            if pad_dur > 0.005:  # more than 5ms padding needed
                silence_wav = output_path.parent / f"silence_{output_path.name}"
                create_silence(pad_dur, silence_wav)
                
                # Concat the converted audio and the silence padding
                concat_audio_files([temp_wav, silence_wav], output_path)
                
                # Cleanup temp files
                if temp_wav.exists():
                    os.remove(temp_wav)
                if silence_wav.exists():
                    os.remove(silence_wav)
            else:
                # If padding is negligible, rename temp_wav to output_path
                if temp_wav.exists():
                    if output_path.exists():
                        os.remove(output_path)
                    os.rename(temp_wav, output_path)
                    
        return output_path
    except subprocess.CalledProcessError as e:
        stderr_msg = e.stderr.decode("utf-8") if e.stderr else "No stderr details"
        logger.error(f"FFmpeg segment processing failed: {stderr_msg}")
        raise FFmpegError(f"Segment processing failed: {stderr_msg}") from e
    except Exception as e:
        logger.error(f"Unexpected error in process_audio_segment: {e}")
        raise FFmpegError(f"Segment processing failed: {e}") from e




def concat_audio_files(file_list: List[Path], output_path: Path) -> Path:
    """
    Concatenates multiple WAV audio files using the FFmpeg concat demuxer.
    All input files must have the same format (16kHz PCM Mono WAV).
    """
    if not file_list:
        raise ValueError("Cannot concatenate an empty list of files.")
        
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Create a temporary list file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        list_file_path = Path(f.name)
        for filepath in file_list:
            # Escape path single quotes for ffmpeg
            escaped_path = str(filepath.resolve()).replace("'", "'\\''")
            f.write(f"file '{escaped_path}'\n")

    try:
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_file_path),
            "-c", "copy",
            str(output_path)
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
        return output_path
    except subprocess.CalledProcessError as e:
        stderr_msg = e.stderr.decode("utf-8") if e.stderr else "No stderr details"
        logger.error(f"Concat failed: {stderr_msg}")
        raise FFmpegError(f"Concat failed: {stderr_msg}") from e
    finally:
        if list_file_path.exists():
            os.remove(list_file_path)


def mix_audio_ducking(
    original_audio: Path,
    dubbed_audio: Path,
    segments: List[Dict[str, Any]],
    output_path: Path,
    ducking_volume: float
) -> Path:
    """
    Applies audio ducking to the original audio when speech segments are active,
    then mixes it with the dubbed audio track.
    """
    if not original_audio.exists():
        raise FileNotFoundError(f"Original audio file not found: {original_audio}")
    if not dubbed_audio.exists():
        raise FileNotFoundError(f"Dubbed audio file not found: {dubbed_audio}")
        
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Build volume ducking expression
    if not segments:
        # No speech segments: no ducking, just mix or use original
        volume_expr = "1.0"
    else:
        # Sum of indicator functions for speech activity
        indicators = []
        for seg in segments:
            start = seg["start"]
            end = seg["end"]
            indicators.append(f"between(t,{start:.3f},{end:.3f})")
        
        summed_indicators = " + ".join(indicators)
        volume_expr = f"1.0 - (1.0 - {ducking_volume}) * min(1, {summed_indicators})"

    # Construct the complex filter for ducking and mixing
    # [0:a] is original_audio, [1:a] is dubbed_audio
    # 1. Apply volume envelope to [0:a] -> [bg]
    # 2. Mix [bg] and [1:a] -> [out]
    try:
        cmd = [
            "ffmpeg", "-y",
            "-i", str(original_audio),
            "-i", str(dubbed_audio),
            "-filter_complex", 
            f"[0:a]volume=eval=frame:volume='{volume_expr}'[bg];[bg][1:a]amix=inputs=2:duration=first:dropout_transition=0[out]",
            "-map", "[out]",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            str(output_path)
        ]
        
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
        logger.info(f"Successfully mixed background audio and dubbed speech with ducking volume {ducking_volume}")
        return output_path
    except subprocess.CalledProcessError as e:
        stderr_msg = e.stderr.decode("utf-8") if e.stderr else "No stderr details"
        logger.error(f"Ducking and mixing failed: {stderr_msg}")
        raise FFmpegError(f"Ducking and mixing failed: {stderr_msg}") from e


def replace_video_audio(video_path: Path, audio_path: Path, output_path: Path) -> Path:
    """
    Combines the video stream of the original file with the new dubbed audio.
    Ensures maximum compatibility across VLC, Windows Media Player, Chrome, and Ubuntu Video Player.
    - If the input video is already h264, copies it stream-losslessly to avoid re-encoding.
    - Otherwise, transcodes the video to H.264 (libx264) with yuv420p pixel format.
    - Validates both input files before muxing.
    - If the audio stream is shorter than the video stream, pads it with silence.
    - If the audio stream is longer, trims it to match the video duration.
    """
    logger.info(f"Initiating video/audio muxing for output: {output_path.name}")
    
    # 1. Validation of input files
    if not video_path.exists():
        logger.error(f"Muxing failed: Video file not found: {video_path}")
        raise FileNotFoundError(f"Video file not found: {video_path}")
    if not audio_path.exists():
        logger.error(f"Muxing failed: Audio file not found: {audio_path}")
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
    try:
        video_probe = ffmpeg.probe(str(video_path))
        has_video = any(s.get("codec_type") == "video" for s in video_probe.get("streams", []))
        if not has_video:
            logger.error(f"Muxing failed: Input video {video_path.name} contains no video stream.")
            raise ValueError(f"Input video file does not contain any video stream.")
    except Exception as e:
        logger.error(f"Validation failed for video file {video_path.name}: {e}")
        raise ValueError(f"Invalid video file: {e}") from e

    try:
        audio_probe = ffmpeg.probe(str(audio_path))
        has_audio = any(s.get("codec_type") == "audio" for s in audio_probe.get("streams", []))
        if not has_audio:
            logger.error(f"Muxing failed: Input audio {audio_path.name} contains no audio stream.")
            raise ValueError(f"Input audio file does not contain any audio stream.")
    except Exception as e:
        logger.error(f"Validation failed for audio file {audio_path.name}: {e}")
        raise ValueError(f"Invalid audio file: {e}") from e

    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        # 2. Extract media metadata & check video codec
        video_codec = None
        for stream in video_probe.get("streams", []):
            if stream.get("codec_type") == "video":
                video_codec = stream.get("codec_name")
                break
                
        video_dur = get_media_duration(video_path)
        audio_dur = get_media_duration(audio_path)
        logger.info(f"Video codec detected: '{video_codec}'. Video duration: {video_dur:.2f}s, Audio duration: {audio_dur:.2f}s")
        
        # 3. Determine video codec options
        # If input codec is already h264, copy the stream. Otherwise transcode to libx264 + yuv420p for max player compatibility.
        if video_codec == "h264":
            logger.info("Video stream is already H.264. Using stream copy (-c:v copy) to save processing time.")
            video_opts = ["-c:v", "copy"]
        else:
            logger.info(f"Video stream uses '{video_codec}' codec. Transcoding to universally compatible H.264 (libx264/yuv420p) to prevent black screen issues.")
            video_opts = [
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "18",
                "-pix_fmt", "yuv420p"
            ]
            
        # 4. Construct the dynamic FFmpeg command
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(audio_path)
        ]
        
        # Handle audio padding if the audio stream is shorter than the video stream
        if audio_dur < video_dur - 0.05:
            logger.info(f"Audio track is shorter than video track by {video_dur - audio_dur:.2f}s. Padding with silence using apad filter.")
            cmd.extend([
                "-filter_complex", f"[1:a]apad=whole_dur={video_dur}[aout]",
                "-map", "0:v:0",
                "-map", "[aout]"
            ])
        else:
            if audio_dur > video_dur + 0.05:
                logger.info(f"Audio track is longer than video track by {audio_dur - video_dur:.2f}s. Trimming audio stream to fit.")
            cmd.extend([
                "-map", "0:v:0",
                "-map", "1:a:0"
            ])
            
        # Video options
        cmd.extend(video_opts)
        
        # Audio options (encode to standard AAC for max compatibility) and duration constraints
        cmd.extend([
            "-c:a", "aac",
            "-shortest",
            "-t", f"{video_dur:.3f}",
            str(output_path)
        ])
        
        logger.info(f"Executing muxing command: {' '.join(cmd)}")
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
        logger.info(f"Video/audio merge completed successfully. Output saved to: {output_path}")
        return output_path
        
    except subprocess.CalledProcessError as e:
        stderr_msg = e.stderr.decode("utf-8") if e.stderr else "No stderr details"
        logger.error(f"FFmpeg video/audio replacement failed: {stderr_msg}")
        raise FFmpegError(f"Video audio replace failed: {stderr_msg}") from e
    except Exception as e:
        logger.error(f"Unexpected error during video/audio replacement: {e}")
        raise FFmpegError(f"Video audio replace failed: {e}") from e
