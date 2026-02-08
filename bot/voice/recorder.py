from typing import Dict

from datetime import datetime
from zoneinfo import ZoneInfo
from discord.ext import voice_recv
import sqlite3
import threading
import queue
import time

from bot.voice.user_track import UserTrack

from bot.utils.file_utils import (
    create_session_folder,
    create_user_wav_path,
    safe_close_wav,
    save_metadata_checkpoint
)
from utils.logger import logger


class Recorder(voice_recv.AudioSink):

    def __init__(self, channel=None, title=None):
        super().__init__()
        
        from bot.utils import config

        # ----- Session -----
        timestamp = datetime.now(ZoneInfo("Asia/Colombo")).isoformat(timespec="milliseconds")
        self.session_dir, self.users_dir = create_session_folder()

        self.start_time = datetime.now()

        # ----- Track Storage -----
        self.tracks : Dict[int, UserTrack] = {}

        # ----- Metadata -----
        self.metadata = {
            "session_start": timestamp,
            "session_end": None,
            "title": title,
            "participant_count": 0,
            "models": {
                "transcriber": {
                    "model": config.WHISPER_MODEL,
                    "device": config.DEVICE,
                    "compute_type": config.COMPUTE_TYPE
                },
                "summarizer": {
                    "model": config.LLM_MODEL
                }
            },
            "channel": {
                "id": str(channel.id) if channel else None,
                "name": channel.name if channel else None,
                "category_id": str(channel.category.id) if channel and channel.category else None,
                "category_name": channel.category.name if channel and channel.category else None
            }
        }
        
        # ----- Meeting Database -----
        self.db_path = self.session_dir / "meeting.db"
        self._init_db()
        
        # ----- Threaded Event Logger -----
        self.event_queue = queue.Queue()
        self.stop_event_logger = threading.Event()
        self.logger_thread = threading.Thread(target=self._event_logger_worker, daemon=True)
        self.logger_thread.start()

    def _init_db(self):
        """Initialize the meeting database with events, notes, and transcriptions tables"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        # 1. Voice Events table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                user_id TEXT NOT NULL,
                
                -- Before states
                before_channel_id TEXT,
                before_channel_name TEXT,
                before_deaf BOOLEAN,
                before_mute BOOLEAN,
                before_self_mute BOOLEAN,
                before_self_deaf BOOLEAN,
                before_self_stream BOOLEAN,
                before_self_video BOOLEAN,
                before_suppress BOOLEAN,
                before_afk BOOLEAN,
                before_requested_to_speak_at TEXT,
                
                -- After states
                after_channel_id TEXT,
                after_channel_name TEXT,
                after_deaf BOOLEAN,
                after_mute BOOLEAN,
                after_self_mute BOOLEAN,
                after_self_deaf BOOLEAN,
                after_self_stream BOOLEAN,
                after_self_video BOOLEAN,
                after_suppress BOOLEAN,
                after_afk BOOLEAN,
                after_requested_to_speak_at TEXT
            )
        """)
        
        # 2. Meeting Notes table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                user_id TEXT NOT NULL,
                content TEXT NOT NULL
            )
        """)

        # 3. Transcriptions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transcriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                user_id TEXT NOT NULL,
                text TEXT NOT NULL
            )
        """)
        
        # 4. Users lookup table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                user_name TEXT NOT NULL,
                nick_name TEXT,
                is_bot BOOLEAN NOT NULL,
                join_offset_ms INTEGER NOT NULL
            )
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp_events ON events(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp_notes ON notes(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp_trans ON transcriptions(timestamp)")
        
        conn.commit()
        conn.close()

    # -----------------------------------------------------

    def wants_opus(self):
        return False

    # -----------------------------------------------------

    def current_offset_ms(self):

        delta = datetime.now() - self.start_time
        return int(delta.total_seconds() * 1000)
    
    # -----------------------------------------------------
    # Event Logging
    # -----------------------------------------------------
    
    # Event Logging
    # -----------------------------------------------------

    def log_event(self, member, before, after):
        """Push a voice state transition to the background logging queue"""
        
        # Capture current time immediately to ensure accuracy
        timestamp = datetime.now(ZoneInfo("Asia/Colombo")).isoformat(timespec="milliseconds")
        
        # Helper to extract channel info
        def get_chan_id(state): return str(state.channel.id) if state.channel else None
        def get_chan_name(state): return state.channel.name if state.channel else None
        def get_iso_time(attr): return attr.isoformat() if attr else None

        # Prepare payload for the background thread
        data = (
            timestamp, str(member.id),
            
            get_chan_id(before), get_chan_name(before), before.deaf, before.mute,
            before.self_mute, before.self_deaf, before.self_stream,
            before.self_video, before.suppress, before.afk, get_iso_time(before.requested_to_speak_at),
            
            get_chan_id(after), get_chan_name(after), after.deaf, after.mute,
            after.self_mute, after.self_deaf, after.self_stream,
            after.self_video, after.suppress, after.afk, get_iso_time(after.requested_to_speak_at)
        )
        
        self.event_queue.put(("events", data))
        logger.debug(f"Queued voice state transition for {member.name}")

    def log_note(self, member, content):
        """Push a meeting note (text message) to the background logging queue"""
        timestamp = datetime.now(ZoneInfo("Asia/Colombo")).isoformat(timespec="milliseconds")
        
        data = (timestamp, str(member.id), content)
        self.event_queue.put(("notes", data))
        logger.info(f"Note logged by {member.name}: {content[:30]}...")

    def _event_logger_worker(self):
        """Worker thread that writes events from the queue to the database"""
        while not self.stop_event_logger.is_set() or not self.event_queue.empty():
            try:
                # Get item from queue
                table, data = self.event_queue.get(timeout=0.5)
                
                conn = sqlite3.connect(str(self.db_path))
                cursor = conn.cursor()
                
                if table == "events":
                    cursor.execute("""
                        INSERT INTO events (
                            timestamp, user_id,
                            before_channel_id, before_channel_name, before_deaf, before_mute, 
                            before_self_mute, before_self_deaf, before_self_stream, 
                            before_self_video, before_suppress, before_afk, before_requested_to_speak_at,
                            after_channel_id, after_channel_name, after_deaf, after_mute, 
                            after_self_mute, after_self_deaf, after_self_stream, 
                            after_self_video, after_suppress, after_afk, after_requested_to_speak_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, data)
                elif table == "notes":
                    cursor.execute("""
                        INSERT INTO notes (timestamp, user_id, content)
                        VALUES (?, ?, ?)
                    """, data)
                
                conn.commit()
                conn.close()
                self.event_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Event logger thread error: {e}")
                time.sleep(1)

    # -----------------------------------------------------
    # Add User Track
    # -----------------------------------------------------

    def add_user(self, user):
        filepath = create_user_wav_path(self.users_dir, user)
        track = UserTrack(filepath)
        self.tracks[user.id] = track

        offset = self.current_offset_ms()
        nick = user.display_name if user.display_name != user.name else None

        # Store user info in DB instead of metadata
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""
            INSERT OR REPLACE INTO users (user_id, user_name, nick_name, is_bot, join_offset_ms)
            VALUES (?, ?, ?, ?, ?)
        """, (str(user.id), user.name, nick, user.bot, offset))
        conn.commit()
        conn.close()

        # Update non-bot participant count in metadata
        if not user.bot:
            self.metadata["participant_count"] = len([t for uid, t in self.tracks.items() if not getattr(t, 'is_bot', False)]) # This is a bit complex, let's simplify

        logger.info(f"Adding track for new user: {user.display_name} ({user.id})")

    async def _update_participant_count(self):
        """Helper to keep participant count updated"""
        # This will be called from outside if needed or calculated at end
        pass

    # -----------------------------------------------------
    # Main Audio Router
    # -----------------------------------------------------
    def write(self, user, data):

        if not data.pcm:
            return

        # Add track dynamically
        if user.id not in self.tracks:
            self.add_user(user)
        
        self.tracks[user.id].enqueue(data.pcm)

    # -----------------------------------------------------
    # Cleanup
    # -----------------------------------------------------

    def cleanup(self):
        """Cleanup recorder resources correctly"""
        # 1. Stop the event logger thread
        logger.info("Cleaning up recorder. Finalizing logs...")
        self.stop_event_logger.set()
        if hasattr(self, 'logger_thread'):
            self.logger_thread.join(timeout=5.0)

        # 2. Stop all user tracks
        for track in self.tracks.values():
            track.stop()

        # 3. Finalize Metadata
        self.metadata["session_end"] = datetime.now(ZoneInfo("Asia/Colombo")).isoformat(timespec="milliseconds")
        
        # Calculate final non-bot participant count from DB
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_bot = 0")
        self.metadata["participant_count"] = cursor.fetchone()[0]
        conn.close()

        save_metadata_checkpoint(self.session_dir, self.metadata)
