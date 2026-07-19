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
        
        # Run using ffmpeg-python
        stream = ffmpeg.input(str(input_path))
        stream = ffmpeg.filter(stream, "atempo", temp_ratio) if len(filters) == 1 else stream.filter_("afir") # Note: filter_ is safer
        
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
    Keeps the video codec (copy) and encodes audio to AAC for max compatibility.
    """
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac",
            "-shortest",
            str(output_path)
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
        logger.info(f"Video dub merge completed. Output path: {output_path}")
        return output_path
    except subprocess.CalledProcessError as e:
        stderr_msg = e.stderr.decode("utf-8") if e.stderr else "No stderr details"
        logger.error(f"Video/audio replacement failed: {stderr_msg}")
        raise FFmpegError(f"Video audio replace failed: {stderr_msg}") from e
