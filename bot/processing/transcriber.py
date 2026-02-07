import sqlite3
import json
import bot.utils.config as config
from pathlib import Path
from datetime import datetime, timedelta
import time
from zoneinfo import ZoneInfo
from faster_whisper import WhisperModel

COLOMBO_TZ = ZoneInfo("Asia/Colombo")

def get_connection(db_path):
    return sqlite3.connect(db_path)

def init_db(db_path):
    with get_connection(db_path) as conn:
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

def insert_transcript(db_path, timestamp, user_id, username, text):
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO transcripts (timestamp, user_id, username, text)
            VALUES (?, ?, ?, ?)
            """,
            (timestamp, str(user_id), username, text)
        )
        conn.commit()

def run_transcription(session_dir, whisper_model=config.WHISPER_MODEL, device=config.DEVICE, compute_type=config.COMPUTE_TYPE, hf_cache_dir=config.HF_CACHE_DIR):
    session_path = Path(session_dir) if not isinstance(session_dir, Path) else session_dir
    db_path = session_path / "transcriptions.db"
    metadata_path = session_path / "metadata.json"
    
    for _ in range(5):  # Retry mechanism for file access
        if metadata_path.exists():
            break
        elif _ == 4:
             raise FileNotFoundError(f"metadata.json not found at {metadata_path} after multiple attempts.")
         
        print(f"Waiting for metadata.json to be available at {metadata_path}...")
        time.sleep(2)

    # Initialize Database
    init_db(db_path)

    # Load Metadata
    with open(metadata_path, "r", encoding="utf8") as f:
        metadata = json.load(f)
    
    session_start = datetime.fromisoformat(metadata["session_start"])

    # Load model with dynamic settings from config
    print(f"Loading Whisper model: {whisper_model} on {device}...")
    model = WhisperModel(
        whisper_model,
        device=device,
        compute_type=compute_type,
        download_root=hf_cache_dir
    )
    print("Model loaded successfully. Starting transcription...")

    # Process user audio files based on metadata
    for user_id, user_info in metadata["users"].items():
        name = user_info["name"]
        join_offset_ms = user_info["join_offset_ms"]
        
        # Look for the wav file
        audio_path = session_path / "users" / f"{user_id}.{name}.wav"
        
        if not audio_path.exists():
            print(f"Warning: Audio file not found for {name}: {audio_path}")
            continue

        print(f"Transcribing {name}...")
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
                name,
                segment.text.strip()
            )

    # Final Step: Re-order the table physically and Export
    print("Finalizing database (sorting rows)...")
    with get_connection(db_path) as conn:
        # 1. Create a sorted temporary table
        conn.execute("CREATE TABLE transcripts_new AS SELECT * FROM transcripts ORDER BY timestamp ASC")
        
        # 2. Replace old table with sorted one
        conn.execute("DROP TABLE transcripts")
        conn.execute("ALTER TABLE transcripts_new RENAME TO transcripts")
        
        # 3. Add an index for future fast lookups
        conn.execute("CREATE INDEX idx_timestamp ON transcripts(timestamp)")
        conn.commit()

        # 4. Stream rows to file (low memory usage)
        export_path = session_path / "transcript.txt"
        cursor = conn.execute("SELECT timestamp, username, text FROM transcripts") # No ORDER BY needed now
        
        with open(export_path, "w", encoding="utf-8") as f:
            for timestamp, username, text in cursor:
                dt = datetime.fromisoformat(timestamp)
                pretty_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"[{pretty_time}] {username}: {text}\n")
            
    print(f"Transcription finished. Full transcript saved to {export_path}")
