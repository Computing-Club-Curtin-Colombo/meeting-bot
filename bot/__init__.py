from discord.ext import commands
from typing import Dict, Optional

class GuildSession:
    """Holds the recording state for a specific guild."""
    def __init__(self):
        self.voice_client = None
        self.recording = False
        self.recorder = None
        self.transcription_webhook = None

class MeetingBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._sessions: Dict[int, GuildSession] = {}

    def get_session(self, guild_id: int) -> GuildSession:
        if guild_id not in self._sessions:
            self._sessions[guild_id] = GuildSession()
        return self._sessions[guild_id]

    async def close(self):
        """Standard cleanup when bot is shutting down."""
        print("Bot is shutting down...")
        
        from bot.processing.pipeline import spawn_processing
        
        for guild_id, session in self._sessions.items():
            if session.recording:
                session.recording = False
                if session.voice_client and session.voice_client.is_listening():
                    session.voice_client.stop_listening()
                
                if session.recorder:
                    session.recorder.cleanup()
                    webhook_url = session.transcription_webhook.url if session.transcription_webhook else None
                    spawn_processing(session.recorder.session_dir, webhook_url=webhook_url)

            if session.voice_client:
                await session.voice_client.disconnect()
            
        await super().close()