from bot import MeetingBot
import bot.utils.config as config
from bot.voice.recorder import Recorder
from bot.processing.pipeline import spawn_processing
from discord import FFmpegPCMAudio, Interaction
from discord.ext import voice_recv

def setup_voice_commands(bot: MeetingBot):

    # ---------- Join Command ----------
    @bot.tree.command(name="join", description="Make the bot join your voice channel")
    async def join(interaction: Interaction):
        if interaction.user.voice is None:
            await interaction.response.send_message(
                "You must be in a voice channel",
                ephemeral=True
            )
            return

        # Defer immediately
        await interaction.response.defer(ephemeral=True)

        channel = interaction.user.voice.channel
        bot.voice_client = await channel.connect(cls=voice_recv.VoiceRecvClient)

        await interaction.followup.send(
            "Joined voice channel",
            ephemeral=True
        )


    # ---------- Start Recording ----------
    @bot.tree.command(name="record", description="Start recording meeting")
    async def record(interaction: Interaction):
        
        if bot.voice_client is None:
            await interaction.response.send_message(
                "Bot not in voice channel!",
                ephemeral=True
            )
            return

        # Defer immediately
        await interaction.response.defer(ephemeral=True)

        bot.recorder = Recorder()
        bot.voice_client.listen(bot.recorder)
        bot.recording = True
        
        await interaction.followup.send(
            "Recording started",
            ephemeral=True
        )
        
        # Stop if already speaking
        if bot.voice_client.is_playing():
            bot.voice_client.stop()

        # Play audio using FFmpeg
        audio = FFmpegPCMAudio(f"{config.SPEECH_CACHE_DIR}/start.mp3")
        bot.voice_client.play(audio)



    # ---------- Stop Recording ----------
    @bot.tree.command(name="stop", description="Stop recording meeting")
    async def stop(interaction: Interaction):
        # Defer immediately
        await interaction.response.defer(ephemeral=True)
        
        bot.recording = False

        if bot.voice_client and bot.voice_client.is_listening():
            bot.voice_client.stop_listening()

            await interaction.followup.send(
                "Recording stopped. Processing transcription...",
                ephemeral=True
            )
            
            # Stop if already speaking
            if bot.voice_client.is_playing():
                bot.voice_client.stop()

            # Play audio using FFmpeg
            audio = FFmpegPCMAudio(f"{config.SPEECH_CACHE_DIR}/stop.mp3")
            bot.voice_client.play(audio)
            
            # Spawn processing (non-blocking)
            if bot.recorder:
                print("model:", config.WHISPER_MODEL)
                print("device:", config.DEVICE)
                print("compute:", config.COMPUTE_TYPE)
                
                spawn_processing(bot.recorder.session_dir, config.WHISPER_MODEL, config.DEVICE, config.COMPUTE_TYPE, config.HF_CACHE_DIR)
        else:
            await interaction.followup.send(
                "No active recording to stop",
                ephemeral=True
            )
