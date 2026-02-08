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

    def __init__(self, channel=None, title=None, model=None, device=None, compute_type=None):
        super().__init__()
        
        from bot.utils import config
        self.model = model or config.WHISPER_MODEL
        self.device = device or config.DEVICE
        self.compute_type = compute_type or config.COMPUTE_TYPE

        # ----- Session -----
        timestamp = datetime.now(ZoneInfo("Asia/Colombo")).isoformat(timespec="milliseconds")
        self.session_dir, self.users_dir = create_session_folder()

        self.start_time = datetime.now()

        # ----- Track Storage -----
        self.tracks : Dict[int, UserTrack] = {}

        # ----- Metadata -----
        self.metadata = {
            "session_start": timestamp,
            "title": title,
            "whisper": {
                "model": self.model,
                "device": self.device,
                "compute_type": self.compute_type
            },
            "channel": {
                "id": str(channel.id) if channel else None,
                "name": channel.name if channel else None,
                "category_id": str(channel.category.id) if channel and channel.category else None,
                "category_name": channel.category.name if channel and channel.category else None
            },
            "users": {}
        }
        
        # ----- Events Database -----
        self.events_db_path = self.session_dir / "events.db"
        self._init_events_db()
        
        # ----- Threaded Event Logger -----
        self.event_queue = queue.Queue()
        self.stop_event_logger = threading.Event()
        self.logger_thread = threading.Thread(target=self._event_logger_worker, daemon=True)
        self.logger_thread.start()

    def _init_events_db(self):
        """Initialize the events database with columns for all VoiceState attributes"""
        conn = sqlite3.connect(str(self.events_db_path))
        cursor = conn.cursor()
        
        # We store both 'before' and 'after' states for all attributes
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                offset_ms INTEGER NOT NULL,
                user_id TEXT NOT NULL,
                user_name TEXT NOT NULL,
                
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
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON events(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_offset ON events(offset_ms)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user ON events(user_id)")

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user ON events(user_id)")
        
        # Table for meeting notes (user messages in the meeting thread)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                offset_ms INTEGER NOT NULL,
                user_id TEXT NOT NULL,
                user_name TEXT NOT NULL,
                content TEXT NOT NULL
            )
        """)
        
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
        
        # Capture current time and offset immediately to ensure accuracy
        timestamp = datetime.now(ZoneInfo("Asia/Colombo")).isoformat(timespec="milliseconds")
        offset_ms = self.current_offset_ms()
        
        # Helper to extract channel info
        def get_chan_id(state): return str(state.channel.id) if state.channel else None
        def get_chan_name(state): return state.channel.name if state.channel else None
        def get_iso_time(attr): return attr.isoformat() if attr else None

        # Prepare payload for the background thread
        data = (
            timestamp, offset_ms, str(member.id), member.name,
            
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
        offset_ms = self.current_offset_ms()
        
        data = (timestamp, offset_ms, str(member.id), member.name, content)
        self.event_queue.put(("notes", data))
        logger.info(f"Note logged by {member.name}: {content[:30]}...")

    def _event_logger_worker(self):
        """Worker thread that writes events from the queue to the database"""
        while not self.stop_event_logger.is_set() or not self.event_queue.empty():
            try:
                # Get item from queue
                table, data = self.event_queue.get(timeout=0.5)
                
                conn = sqlite3.connect(str(self.events_db_path))
                cursor = conn.cursor()
                
                if table == "events":
                    cursor.execute("""
                        INSERT INTO events (
                            timestamp, offset_ms, user_id, user_name,
                            before_channel_id, before_channel_name, before_deaf, before_mute, 
                            before_self_mute, before_self_deaf, before_self_stream, 
                            before_self_video, before_suppress, before_afk, before_requested_to_speak_at,
                            after_channel_id, after_channel_name, after_deaf, after_mute, 
                            after_self_mute, after_self_deaf, after_self_stream, 
                            after_self_video, after_suppress, after_afk, after_requested_to_speak_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, data)
                elif table == "notes":
                    cursor.execute("""
                        INSERT INTO notes (timestamp, offset_ms, user_id, user_name, content)
                        VALUES (?, ?, ?, ?, ?)
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

        self.metadata["users"][str(user.id)] = {
            "name": user.name,
            "join_offset_ms": offset
        }
        logger.info(f"Adding track for new user: {user.name} ({user.id})")

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

        # 3. Save final metadata
        save_metadata_checkpoint(self.session_dir, self.metadata)
