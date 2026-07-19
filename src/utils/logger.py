import logging
import sys
from pathlib import Path
from typing import Optional
from config import LOG_FILE_PATH, LOG_LEVEL


# ANSI Color Codes for Colored Console Output
class ConsoleColors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    
    # Text colors
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    
    # Background colors
    BG_BLACK = "\033[40m"
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"
    BG_MAGENTA = "\033[45m"
    BG_CYAN = "\033[46m"
    BG_WHITE = "\033[47m"


class ColoredFormatter(logging.Formatter):
    """
    Custom formatter to inject ANSI color codes into terminal logging output based on log levels.
    """
    
    COLORS = {
        logging.DEBUG: ConsoleColors.CYAN,
        logging.INFO: ConsoleColors.GREEN,
        logging.WARNING: ConsoleColors.YELLOW,
        logging.ERROR: ConsoleColors.RED,
        logging.CRITICAL: ConsoleColors.BOLD + ConsoleColors.BG_RED + ConsoleColors.WHITE,
    }

    def format(self, record: logging.LogRecord) -> str:
        log_color = self.COLORS.get(record.levelno, ConsoleColors.RESET)
        
        # Format parts of the message
        timestamp = f"{ConsoleColors.BLUE}{self.formatTime(record, self.datefmt)}{ConsoleColors.RESET}"
        level_name = f"{log_color}{record.levelname:<8}{ConsoleColors.RESET}"
        module_info = f"{ConsoleColors.MAGENTA}{record.name}:{record.lineno}{ConsoleColors.RESET}"
        message = record.getMessage()
        
        return f"[{timestamp}] {level_name} [{module_info}] - {message}"


def setup_logger(name: str = "dubbing_pipeline", log_file: Optional[Path] = LOG_FILE_PATH) -> logging.Logger:
    """
    Sets up a logger with a colored stream handler and a file handler.
    
    Args:
        name: Name of the logger.
        log_file: Optional Path to write log messages to.
        
    Returns:
        A configured logging.Logger instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
    
    # Prevent duplicate handlers if setup is called multiple times
    if logger.handlers:
        return logger

    # 1. Colored Console Stream Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_formatter = ColoredFormatter(
        fmt="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # 2. File Handler (if configured)
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        
        # Standard uncolored formatter for log files
        file_formatter = logging.Formatter(
            fmt="[%(asctime)s] %(levelname)-8s [%(name)s:%(lineno)d] - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger
