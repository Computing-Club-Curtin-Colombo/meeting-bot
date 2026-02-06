import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Discord
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Speech/Audio
START_RECORDING_SPEECH = "Recording started."
STOP_RECORDING_SPEECH = "Recording stopped."
SPEECH_CACHE_DIR = "speech_cache"

# AI / Whisper (Default values, will be overridden by __main__.py)
WHISPER_MODEL = "base"
DEVICE = "cpu"
COMPUTE_TYPE = "int8"
HF_CACHE_DIR = str(Path(__file__).parent.parent.parent / "hf_cache")