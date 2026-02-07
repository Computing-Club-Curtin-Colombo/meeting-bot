import logging
import logging.handlers
import sys
import os
import queue
from datetime import datetime
from pathlib import Path

# ANSI Color codes
class Colors:
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    RESET = "\033[0m"
    GREY = "\033[90m"
    PURPLE = "\033[95m"

class ColoredFormatter(logging.Formatter):
    """Custom formatter to add colors based on log level"""
    
    LEVEL_COLORS = {
        logging.DEBUG: Colors.GREY,
        logging.INFO: Colors.CYAN,
        logging.WARNING: Colors.YELLOW,
        logging.ERROR: Colors.RED,
        logging.CRITICAL: Colors.RED + Colors.BOLD
    }

    def format(self, record):
        timestamp = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        level_color = self.LEVEL_COLORS.get(record.levelno, Colors.RESET)
        
        colored_timestamp = f"{Colors.GREEN}{timestamp}{Colors.RESET}"
        colored_level = f"{level_color}[{record.levelname}]{Colors.RESET}"
        colored_name = f"{Colors.PURPLE}{record.name}:{Colors.RESET}"
        
        return f"{colored_timestamp} {colored_level} {colored_name} {record.getMessage()}"

def setup_logger(name="bot", log_to_file=True):
    """Sets up a non-blocking logger using QueueHandler and QueueListener"""
    
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    
    if logger.handlers:
        return logger

    # Create queue for non-blocking logging
    log_queue = queue.Queue(-1)
    queue_handler = logging.handlers.QueueHandler(log_queue)
    logger.addHandler(queue_handler)

    handlers = []

    # 1. Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(ColoredFormatter())
    handlers.append(console_handler)
    
    # 2. File Handler
    if log_to_file:
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)
        log_filename = logs_dir / f"bot_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"
        
        file_handler = logging.FileHandler(log_filename, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_format = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        file_handler.setFormatter(file_format)
        handlers.append(file_handler)

    # Enable ANSI colors on Windows
    if os.name == 'nt':
        os.system('')

    # Setup and start background listener
    listener = logging.handlers.QueueListener(log_queue, *handlers, respect_handler_level=True)
    listener.start()
    
    # Store listener to prevent GC and allow shutdown
    logger.listener = listener
    
    if log_to_file:
        logger.info(f"Logging initialized (Non-blocking). File: {log_filename}")

    return logger

# Global logger instance
logger = setup_logger()
base_logger = logging.getLogger()
if not base_logger.handlers:
    base_logger.addHandler(logging.handlers.QueueHandler(queue.Queue(-1))) # Attach to same queue if needed
