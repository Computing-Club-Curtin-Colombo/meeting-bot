from typing import Dict

import datetime
from zoneinfo import ZoneInfo
from discord.ext import voice_recv

from bot.voice.user_track import UserTrack

from bot.utils.file_utils import (
    create_session_folder,
    create_user_wav_path,
    safe_close_wav,
    save_metadata_checkpoint
)


class Recorder(voice_recv.AudioSink):

    def __init__(self):
        super().__init__()

        # ----- Session -----
        timestamp = datetime.now(ZoneInfo("Asia/Colombo")).isoformat(timespec="microseconds")
        self.session_dir, self.users_dir = create_session_folder()

        self.start_time = datetime.datetime.now()

        # ----- Track Storage -----
        self.tracks : Dict[int, UserTrack] = {}

        # ----- Metadata -----
        self.metadata = {
            "session_start": timestamp,
            "users": {}
        }

    # -----------------------------------------------------

    def wants_opus(self):
        return False

    # -----------------------------------------------------

    def current_offset_ms(self):

        delta = datetime.datetime.now() - self.start_time
        return int(delta.total_seconds() * 1000)

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

    # -----------------------------------------------------
    # Main Audio Router
    # -----------------------------------------------------

    def write(self, user, data):

        if not data.pcm:
            return

        # Add track dynamically
        if user.id not in self.tracks:
            self.add_user(user)

        packet_size = len(data.pcm)
        silence = bytes(packet_size)
        
        self.tracks[user.id].enqueue(data.pcm)

    # -----------------------------------------------------
    # Cleanup
    # -----------------------------------------------------

    def cleanup(self):

        # Stop all user tracks
        for track in self.tracks.values():
            track.stop()

        save_metadata_checkpoint(self.session_dir, self.metadata)
