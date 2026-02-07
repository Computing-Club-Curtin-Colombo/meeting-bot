from bot import MeetingBot
import bot.utils.config as config
from bot.voice.recorder import Recorder
from bot.processing.pipeline import spawn_processing
from discord import FFmpegPCMAudio, Interaction
from discord.ext import voice_recv
from utils.logger import logger

def setup_voice_commands(bot: MeetingBot):
    
    def get_voice_client(guild):
        """Get the bot's voice client from Discord API, not from stored variable"""
        if not guild:
            return None
        
        # Check if bot is in a voice channel according to Discord
        if guild.me.voice is None:
            return None
        
        # Get the actual voice client from Discord's state
        voice_client = guild.voice_client
        
        # Verify it's connected
        if voice_client and voice_client.is_connected():
            return voice_client
        
        return None

    # ---------- Join Command ----------
    @bot.tree.command(name="join", description="Make the bot join your voice channel")
    async def join(interaction: Interaction):
        # Defer immediately
        await interaction.response.defer(ephemeral=True)

        if interaction.user.voice is None:
            await interaction.followup.send(
                "You must be in a voice channel",
                ephemeral=True
            )
            return

        channel = interaction.user.voice.channel
        logger.info(f"Attempting to join voice channel: {channel.name} ({channel.id})")
        
        bot.voice_client = await channel.connect(cls=voice_recv.VoiceRecvClient)
        
        logger.info(f"Connection established! Bot is now in '{channel.name}'")
        logger.debug(f"Voice client SID: {bot.voice_client.session_id} | Endpoint: {bot.voice_client.endpoint}")

        await interaction.followup.send(
            "Joined voice channel",
            ephemeral=True
        )


    # ---------- Start Recording ----------
    @bot.tree.command(name="record", description="Start recording meeting")
    async def record(interaction: Interaction):
        # Defer immediately
        await interaction.response.defer(ephemeral=True)
        
        # Get voice client from Discord API
        voice_client = get_voice_client(interaction.guild)
        
        if voice_client is None:
            await interaction.followup.send(
                "Bot not in voice channel! Use `/join` first.",
                ephemeral=True
            )
            return

        logger.info(f"Initializing recording session for channel: {voice_client.channel.name}")
        bot.recorder = Recorder(channel=voice_client.channel)
        
        logger.debug(f"Recorder initialized. Session Path: {bot.recorder.session_dir}")
        
        voice_client.listen(bot.recorder)
        bot.recording = True
        logger.info("Recording sink attached and listening successfully.")
        
        await interaction.followup.send(
            "Recording started",
            ephemeral=True
        )
        
        # Stop if already speaking
        if voice_client.is_playing():
            voice_client.stop()

        # Play audio using FFmpeg
        audio = FFmpegPCMAudio(f"{config.SPEECH_CACHE_DIR}/start.mp3")
        voice_client.play(audio)



    # ---------- Stop Recording ----------
    @bot.tree.command(name="stop", description="Stop recording meeting")
    async def stop(interaction: Interaction):
        # Defer immediately
        await interaction.response.defer(ephemeral=True)
        
        logger.info(f"Stop request received from {interaction.user}. Finalizing session...")
        
        bot.recording = False

        # Get voice client from Discord API
        voice_client = get_voice_client(interaction.guild)
        
        if voice_client and voice_client.is_listening():
            logger.debug("Detaching recorder sink...")
            voice_client.stop_listening()
            logger.info("Recording stopped successfully.")

            await interaction.followup.send(
                "Recording stopped. Processing transcription...",
                ephemeral=True
            )
            
            # Stop if already speaking
            if voice_client.is_playing():
                voice_client.stop()

            # Play audio using FFmpeg
            audio = FFmpegPCMAudio(f"{config.SPEECH_CACHE_DIR}/stop.mp3")
            voice_client.play(audio)
            
            # Spawn processing (non-blocking)
            if bot.recorder:
                logger.debug(f"Spawning transcription for {bot.recorder.session_dir}")
                logger.debug(f"Model: {config.WHISPER_MODEL} | Device: {config.DEVICE}")
                
                spawn_processing(bot.recorder.session_dir, config.WHISPER_MODEL, config.DEVICE, config.COMPUTE_TYPE, config.HF_CACHE_DIR)
        else:
            await interaction.followup.send(
                "No active recording to stop",
                ephemeral=True
            )
