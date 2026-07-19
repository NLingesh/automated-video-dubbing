import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from src.utils.logger import ConsoleColors


def get_colored_text(text: str, color_code: str) -> str:
    """
    Wraps text with ANSI color codes.
    """
    return f"{color_code}{text}{ConsoleColors.RESET}"


def print_step_banner(step_num: int, message: str) -> None:
    """
    Prints a beautiful styled step banner in the console.
    """
    banner_width = 80
    border = "=" * banner_width
    padding = " " * ((banner_width - len(message) - 12) // 2)
    
    print("\n")
    print(get_colored_text(border, ConsoleColors.CYAN))
    print(get_colored_text(
        f"=== {padding}STEP {step_num}: {message.upper()}{padding} ===", 
        ConsoleColors.BOLD + ConsoleColors.CYAN
    ))
    print(get_colored_text(border, ConsoleColors.CYAN))
    print()


def print_banner() -> None:
    """
    Prints the system startup banner.
    """
    banner_text = """
    ======================================================================
                  AUTOMATED VIDEO DUBBING SYSTEM (AI PRODUCTION)
    ======================================================================
    """
    print(get_colored_text(banner_text, ConsoleColors.BOLD + ConsoleColors.GREEN))


def format_seconds_to_srt_time(seconds: float) -> str:
    """
    Converts a time in seconds (float) to SRT format: HH:MM:SS,mmm
    """
    hours, remainder = divmod(seconds, 3600)
    minutes, remainder = divmod(remainder, 60)
    secs, milliseconds = divmod(remainder, 1)
    
    return f"{int(hours):02d}:{int(minutes):02d}:{int(secs):02d},{int(milliseconds * 1000):03d}"


def generate_srt(segments: List[Dict[str, Any]], output_path: Path) -> Path:
    """
    Generates a standard SubRip (.srt) subtitle file from Whisper segments.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        for idx, segment in enumerate(segments, start=1):
            start_str = format_seconds_to_srt_time(segment["start"])
            end_str = format_seconds_to_srt_time(segment["end"])
            
            # Subtitle block format:
            # Index
            # Start time --> End time
            # Subtitle text (strip to clean any whitespace)
            # Empty line
            f.write(f"{idx}\n")
            f.write(f"{start_str} --> {end_str}\n")
            f.write(f"{segment.get('text', '').strip()}\n\n")
            
    return output_path


def write_execution_report(
    output_path: Path,
    video_name: str,
    duration: float,
    input_language: str,
    output_language: str,
    processing_time: float,
    generated_files: List[str],
    status: str,
    whisper_model: str,
    voice_model: str,
    error_reason: str = ""
) -> Path:
    """
    Generates a report.json summarizing execution details and metrics.
    """
    report_data: Dict[str, Any] = {
        "execution_timestamp": datetime.now().isoformat(),
        "status": status,
        "video": {
            "name": video_name,
            "duration_seconds": duration,
        },
        "languages": {
            "detected_input_language": input_language,
            "output_language": output_language,
        },
        "performance": {
            "total_processing_time_seconds": processing_time,
        },
        "configurations": {
            "whisper_model": whisper_model,
            "voice_model": voice_model,
        },
        "output_files": generated_files,
    }
    
    if error_reason:
        report_data["error_reason"] = error_reason

    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=4)
        
    return output_path
