from discord.ext import commands

class MeetingBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.voice_client = None
        self.recorder = None