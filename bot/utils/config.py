import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

START_RECORDING_SPEECH = "Recording started."
STOP_RECORDING_SPEECH = "Recording stopped."
SPEECH_CACHE_DIR = "speech_cache"