from discord import app_commands, Interaction, FFmpegAudio, FFmpegPCMAudio
import edge_tts
import random

from bot import MeetingBot

def setup_tts_commands(bot: MeetingBot):

    # ---------- SAY COMMAND ----------
    @bot.tree.command(name="say", description="Bot speaks text")
    @app_commands.describe(text="Text for bot to speak")
    async def say(interaction: Interaction, text: str):

        if bot.voice_client is None:
            await interaction.response.send_message(
                "Bot is not in voice channel",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            "Speaking...",
            ephemeral=True
        )

        # Generate speech file
        communicate = edge_tts.Communicate(text)
        await communicate.save("speech.mp3")

        # Stop if already speaking
        if bot.voice_client.is_playing():
            bot.voice_client.stop()

        # Play audio using FFmpeg
        audio = FFmpegPCMAudio("speech.mp3")
        bot.voice_client.play(audio)
