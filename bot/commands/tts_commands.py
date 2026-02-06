from discord import app_commands, Interaction, FFmpegAudio, FFmpegPCMAudio
import edge_tts
import random

from bot import MeetingBot

def setup_tts_commands(bot: MeetingBot):

    # ---------- SAY COMMAND ----------
    @bot.tree.command(name="say", description="Bot speaks text")
    @app_commands.describe(text="Text for bot to speak")
    async def say(interaction: Interaction, text: str):

        session = bot.get_session(interaction.guild_id)

        if session.voice_client is None:
            await interaction.response.send_message(
                "Bot is not in voice channel",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            "Speaking...",
            ephemeral=True
        )
        
        # Unique filename to avoid race conditions
        filename = f"speech_{interaction.id}.mp3"

        # Generate speech file
        communicate = edge_tts.Communicate(text)
        await communicate.save(filename)

        # Stop if already speaking
        if session.voice_client.is_playing():
            session.voice_client.stop()

        # Play audio using FFmpeg
        audio = FFmpegPCMAudio(filename)
        session.voice_client.play(audio)
        
        # Optional: cleanup file after playing (though FFmpeg might hold a lock)
        # For simplicity in this demo, we leave it, but a professional version would use a tempfile.
