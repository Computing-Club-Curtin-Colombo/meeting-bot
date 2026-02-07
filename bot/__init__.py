from discord.ext import commands
import discord
from typing import Dict, Optional

from bot.voice.recorder import Recorder

class MeetingBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.voice_client : Optional[discord.VoiceClient] = None
        self.recording : Optional[bool] = None
        self.recorder : Optional[Recorder] = None