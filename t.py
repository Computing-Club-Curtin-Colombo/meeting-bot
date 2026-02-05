import sounddevice as sd
import numpy as np
from faster_whisper import WhisperModel
from pathlib import Path
from huggingface_hub import snapshot_download
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import json
import sqlite3

# ---------- ENV ----------
load_dotenv()

script_dir = Path(__file__).resolve().parent
hf_cache_dir = script_dir / "hf_cache"
hf_cache_dir.mkdir(parents=True, exist_ok=True)

os.environ["HF_HOME"] = str(hf_cache_dir)

# ---------- MODEL DOWNLOAD ----------
model_path = snapshot_download(
    repo_id="Systran/faster-whisper-small",
    local_dir=str(hf_cache_dir)
)

print("Model ready")

# ---------- LOAD MODEL ----------
model = WhisperModel(
    model_path,
    device="cpu",
    compute_type="int8"
)

COLOMBO_TZ = ZoneInfo("Asia/Colombo")

session_dir = Path("sessions") / "2026-02-06T00-56-43.185_05-30"

DB_PATH = session_dir / "transcriptions.db"


def get_connection():
    return sqlite3.connect(DB_PATH)


def init_db():
    with get_connection() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS transcripts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            user_id TEXT NOT NULL,
            username TEXT NOT NULL,
            text TEXT NOT NULL
        )
        """)
        conn.commit()


def insert_transcript(timestamp, user_id, username, text):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO transcripts (timestamp, user_id, username, text)
            VALUES (?, ?, ?, ?)
            """,
            (timestamp, str(user_id), username, text)
        )
        conn.commit()


def fetch_all_sorted():
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT timestamp, username, text
            FROM transcripts
            ORDER BY timestamp ASC
            """
        ).fetchall()

init_db()

metadata_path = session_dir / "metadata.json"
with open(metadata_path, "r", encoding="utf8") as f:
    metadata = json.load(f)

# ---- Parse session start (must be ISO string in metadata) ----
session_start = datetime.fromisoformat(metadata["session_start"])

for user_id, user_info in metadata["users"].items():

    join_offset_ms = user_info["join_offset_ms"]
    name = user_info["name"]

    user_audio = session_dir / "users" / f"{user_id}.{name}.wav"

    segments, info = model.transcribe(user_audio)

    for segment in segments:

        # ----- Convert segment start to absolute timestamp -----
        absolute_time = (
            session_start
            + timedelta(milliseconds=join_offset_ms)
            + timedelta(seconds=segment.start)
        )

        # Ensure timezone +05:30
        absolute_time = absolute_time.astimezone(COLOMBO_TZ)

        # ISO format with milliseconds
        timestamp_str = absolute_time.isoformat(timespec="milliseconds")

        insert_transcript(
            timestamp_str,
            user_id,
            name,
            segment.text
        )
        
# ---------- Fetch and print all transcripts ----------
rows = fetch_all_sorted()

print(len(rows), "transcriptions for user", name)

for timestamp, username, text in rows:
    print(f"[{timestamp}] {username}: {text}")
