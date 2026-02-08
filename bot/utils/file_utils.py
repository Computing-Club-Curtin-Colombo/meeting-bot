from pathlib import Path
from datetime import datetime
import re
import json
import os
from zoneinfo import ZoneInfo
import edge_tts
import asyncio

from bot.utils.config import SPEECH_CACHE_DIR, START_RECORDING_SPEECH, STOP_RECORDING_SPEECH


# =========================================================
# Session Management
# =========================================================

def create_session_folder(base="sessions"):
    timestamp = (datetime.now(ZoneInfo("Asia/Colombo")).isoformat(timespec="milliseconds")
                 .replace(":", "-")
                 .replace("+", "_")
                 )

    session_dir = Path(base) / timestamp
    users_dir = session_dir / "users"

    users_dir.mkdir(parents=True, exist_ok=True)

    return session_dir, users_dir


def is_session_incomplete(session_dir):
    meta = session_dir / "metadata.json"
    return not meta.exists()


# =========================================================
# File Naming
# =========================================================

def sanitize_filename(name: str):
    return re.sub(r'[<>:"/\\|?*]', "_", name)


def create_user_wav_path(users_dir, user):
    return users_dir / f"{user.id}.wav"


# =========================================================
# JSON Handling
# =========================================================

def atomic_write_json(filepath, data):
    tmp_path = str(filepath) + ".tmp"

    with open(tmp_path, "w", encoding="utf8") as f:
        json.dump(data, f, indent=4)
        f.flush()
        os.fsync(f.fileno())

    os.replace(tmp_path, filepath)


def safe_load_json(filepath, default=None):

    if not filepath.exists():
        return default

    try:
        with open(filepath, "r", encoding="utf8") as f:
            return json.load(f)
    except Exception:
        return default


def save_metadata_checkpoint(session_dir, metadata):
    meta_path = session_dir / "metadata.json"
    atomic_write_json(meta_path, metadata)


# =========================================================
# WAV Helpers
# =========================================================

def safe_close_wav(wav_file):
    try:
        wav_file.close()
    except Exception:
        pass


# =========================================================
# Directory Helpers
# =========================================================

def ensure_dir(path):
    Path(path).mkdir(parents=True, exist_ok=True)


# =========================================================
# File Validation
# =========================================================

def file_is_valid(filepath, min_size=100):
    return filepath.exists() and filepath.stat().st_size > min_size


def list_user_audio_files(session_dir):
    users_dir = session_dir / "users"
    return list(users_dir.glob("*.wav"))


# =========================================================
# Temporary File Helpers
# =========================================================

def create_temp_path(path):
    return Path(str(path) + ".tmp")


# =========================================================
# Prepared Speech Generator
# =========================================================

async def generate_prepared_speech_files(
    speech_map: dict = {
        "start": START_RECORDING_SPEECH,
        "stop": STOP_RECORDING_SPEECH
    },
    output_dir=SPEECH_CACHE_DIR,
    voice="en-AU-WilliamMultilingualNeural"
):
    """
    Generates pre-cached MP3 speech files.

    speech_map example:
    {
        "start": "Recording started.",
        "stop": "Recording stopped."
    }

    Returns:
        dict -> { key: filepath }
    """

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    results = {}

    for key, text in speech_map.items():

        filepath = output_dir / f"{key}.mp3"

        # Skip if already exists
        if filepath.exists():
            results[key] = filepath
            continue

        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(filepath))

        results[key] = filepath

    return results
