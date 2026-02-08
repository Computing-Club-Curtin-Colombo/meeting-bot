import discord
from bot import MeetingBot
import bot.utils.config as config
from bot.voice.recorder import Recorder
from bot.processing.pipeline import spawn_processing
from discord import FFmpegPCMAudio, Interaction, ChannelType
from discord.ext import voice_recv
from utils.logger import logger
from datetime import datetime

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
    @discord.app_commands.describe(
        title="Optional title for the meeting"
    )
    async def record(
        interaction: Interaction, 
        title: str = None
    ):
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

        # Use defaults from global config
        model = config.WHISPER_MODEL
        device = config.DEVICE
        compute_type = config.COMPUTE_TYPE

        logger.info(f"Initializing recording session for channel: {voice_client.channel.name} (Title: {title})")
        bot.recorder = Recorder(
            channel=voice_client.channel, 
            title=title
        )
        
        logger.debug(f"Recorder initialized. Session Path: {bot.recorder.session_dir}")
        
        voice_client.listen(bot.recorder)
        bot.recording = True
        logger.info("Recording sink attached and listening successfully.")
        
        # Create a thread for meeting notes
        try:
            # VoiceChannels (chat in voice) don't support threads. 
            # We must find a compatible TextChannel.
            target_channel = interaction.channel
            if target_channel.type == ChannelType.voice:
                logger.debug("Command invoked in Voice Channel chat. Searching for sibling Text Channel...")
                # 1. Try same category
                if target_channel.category:
                    for ch in target_channel.category.text_channels:
                        target_channel = ch
                        break
                
                # 2. Fallback to any text channel in guild if still pointing to voice
                if target_channel.type == ChannelType.voice:
                    for ch in interaction.guild.text_channels:
                        target_channel = ch
                        break
            
            if target_channel.type == ChannelType.voice:
                logger.error("No compatible text channel found to create meeting notes thread.")
                return

            now = datetime.now()
            day = now.day
            suffix = "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
            date_str = f"{day}{suffix} {now.strftime('%b, %Y | %H:%M')}"
            
            if title:
                thread_title = f"{title} ({date_str})"
            else:
                thread_title = date_str
            
            thread = await target_channel.create_thread(
                name=thread_title,
                auto_archive_duration=10080, # 7 days (max)
                type=ChannelType.public_thread
            )
            logger.info(f"Created meeting notes thread: {thread_title}")
            
            # Store thread ID as an attribute (not in metadata dict to avoid saving to file)
            bot.recorder.thread_id = str(thread.id)
            
            await thread.send(f"**Meeting Started!** Use this thread to add notes. I will log everything here into the meeting database.")
        except Exception as e:
            logger.error(f"Failed to create meeting notes thread: {e}")

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
            
            # Archive the meeting notes thread if it exists
            thread_id = getattr(bot.recorder, "thread_id", None)
            if thread_id:
                try:
                    thread = interaction.guild.get_thread(int(thread_id))
                    if thread:
                        logger.info(f"Archiving meeting notes thread: {thread.name}")
                        await thread.send("Meeting stopped. This thread is now archived.")
                        await thread.edit(archived=True, locked=True)
                except Exception as e:
                    logger.error(f"Failed to archive thread: {e}")

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
                m_meta = bot.recorder.metadata.get("models", {})
                t_meta = m_meta.get("transcriber", {})
                w_model = t_meta.get("model", config.WHISPER_MODEL)
                w_device = t_meta.get("device", config.DEVICE)
                w_compute = t_meta.get("compute_type", config.COMPUTE_TYPE)
                
                logger.debug(f"Spawning transcription for {bot.recorder.session_dir}")
                logger.info(f"Using settings -> Model: {w_model} | Device: {w_device} | Compute: {w_compute}")
                
                spawn_processing(bot.recorder.session_dir, w_model, w_device, w_compute, config.HF_CACHE_DIR)
        else:
            await interaction.followup.send(
                "No active recording to stop",
                ephemeral=True
            )
