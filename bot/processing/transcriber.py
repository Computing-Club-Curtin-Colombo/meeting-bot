import os

# Enable high-speed downloads with progress bars
# These MUST be set before importing huggingface_hub or faster_whisper
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"
os.environ["PYTHONUNBUFFERED"] = "1"

import sqlite3
import json
import bot.utils.config as config
from pathlib import Path
from datetime import datetime, timedelta
import time
from zoneinfo import ZoneInfo
from faster_whisper import WhisperModel
from huggingface_hub import snapshot_download
from utils.logger import logger

COLOMBO_TZ = ZoneInfo("Asia/Colombo")

def get_connection(db_path):
    return sqlite3.connect(db_path)

def init_db(db_path):
    with get_connection(db_path) as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS transcriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            user_id TEXT NOT NULL,
            text TEXT NOT NULL
        )
        """)
        conn.commit()

def insert_transcript(db_path, timestamp, user_id, text):
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO transcriptions (timestamp, user_id, text)
            VALUES (?, ?, ?)
            """,
            (timestamp, str(user_id), text)
        )
        conn.commit()

def run_transcription(session_dir, whisper_model=config.WHISPER_MODEL, device=config.DEVICE, compute_type=config.COMPUTE_TYPE, hf_cache_dir=config.HF_CACHE_DIR):
    session_path = Path(session_dir) if not isinstance(session_dir, Path) else session_dir
    db_path = session_path / "meeting.db"
    metadata_path = session_path / "metadata.json"
    
    for _ in range(5):  # Retry mechanism for file access
        if metadata_path.exists():
            break
        elif _ == 4:
             logger.error(f"metadata.json not found at {metadata_path} after multiple attempts.")
             raise FileNotFoundError(f"metadata.json not found at {metadata_path} after multiple attempts.")
         
        logger.debug(f"Waiting for metadata.json to be available at {metadata_path}...")
        time.sleep(2)

    # Initialize Database
    init_db(db_path)

    # Load Metadata for session start
    with open(metadata_path, "r", encoding="utf8") as f:
        metadata = json.load(f)
    
    session_start = datetime.fromisoformat(metadata["session_start"])

    # Load Users from Database
    with get_connection(db_path) as conn:
        cursor = conn.execute("SELECT user_id, user_name, nick_name, join_offset_ms FROM users")
        members = cursor.fetchall()

    # Load model with dynamic settings from config
    logger.info(f"Loading Whisper model: {whisper_model} on {device}...")
    model = WhisperModel(
        whisper_model,
        device=device,
        compute_type=compute_type,
        download_root=hf_cache_dir
    )
    logger.info("Model loaded successfully. Starting transcription...")

    # Process user audio files based on database records
    for user_id, user_name, nick_name, join_offset_ms in members:
        name_for_logs = nick_name or user_name
        
        # Look for the wav file
        audio_path = session_path / "users" / f"{user_id}.wav"
        
        if not audio_path.exists():
            logger.warning(f"Audio file not found for {name_for_logs}: {audio_path}")
            continue

        logger.info(f"Transcribing {name_for_logs}...")
        segments, info = model.transcribe(str(audio_path), beam_size=5)

        for segment in segments:
            # Calculate absolute timestamp
            absolute_time = (
                session_start
                + timedelta(milliseconds=join_offset_ms)
                + timedelta(seconds=segment.start)
            )
            
            # Ensure correct timezone and format
            absolute_time = absolute_time.astimezone(COLOMBO_TZ)
            timestamp_str = absolute_time.isoformat(timespec="milliseconds")

            # Store in DB to save RAM
            insert_transcript(
                db_path,
                timestamp_str,
                user_id,
                segment.text.strip()
            )

    # Final Step: Re-order the table physically
    logger.info("Finalizing database (sorting rows)...")
    with get_connection(db_path) as conn:
        # 1. Create a sorted temporary table
        conn.execute("CREATE TABLE trans_new AS SELECT * FROM transcriptions ORDER BY timestamp ASC")
        
        # 2. Replace old table with sorted one
        conn.execute("DROP TABLE transcriptions")
        conn.execute("ALTER TABLE trans_new RENAME TO transcriptions")
        
        # 3. Add an index for future fast lookups
        conn.execute("CREATE INDEX IF NOT EXISTS idx_trans_timestamp ON transcriptions(timestamp)")
        conn.commit()

    # Generate Prompt File for LLM
    try:
        from bot.processing.prompt_generator import generate_prompt
        logger.info("Generating PROMPT1 for LLM extraction...")
        generate_prompt(session_dir)
        logger.info("PROMPT1 generated successfully.")
        
        # Trigger LLM Summarization
        from bot.processing.summarizer import run_llm_processing
        run_llm_processing(session_dir)
        
    except Exception as e:
        logger.error(f"Failed to generate PROMPT1 or run LLM: {e}")
    
    # Force exit to ensure the sub-process terminates completely and releases all resources (GPU/RAM)
    import os
    os._exit(0)
