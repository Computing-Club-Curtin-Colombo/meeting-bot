from bot import MeetingBot
from bot.utils.config import SPEECH_CACHE_DIR
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

        session = bot.get_session(interaction.guild_id)
        channel = interaction.user.voice.channel
        session.voice_client = await channel.connect(cls=voice_recv.VoiceRecvClient)

        await interaction.response.send_message(
            "Joined voice channel",
            ephemeral=True
        )


    # ---------- Start Recording ----------
    @bot.tree.command(name="record", description="Start recording meeting")
    async def record(interaction: Interaction):
        
        session = bot.get_session(interaction.guild_id)

        if session.voice_client is None:
            await interaction.response.send_message(
                "Bot not in voice channel!",
                ephemeral=True
            )
            return

        # Defer immediately
        await interaction.response.defer(ephemeral=True)

        session.recorder = Recorder()
        session.voice_client.listen(session.recorder)
        session.recording = True
        
        # Create a webhook to deliver the transcript later
        if not session.transcription_webhook:
            try:
                # We reuse/create a webhook named "Meeting Bot Transcriber"
                webhooks = await interaction.channel.webhooks()
                session.transcription_webhook = next((w for w in webhooks if w.name == "Meeting Bot Transcriber"), None)
                if not session.transcription_webhook:
                    session.transcription_webhook = await interaction.channel.create_webhook(name="Meeting Bot Transcriber")
            except Exception as e:
                print(f"Warning: Could not create webhook for guild {interaction.guild_id}: {e}")

        await interaction.followup.send(
            "Recording started",
            ephemeral=True
        )
        
        # play start sound
        if session.voice_client.is_playing():
            session.voice_client.stop()
        audio = FFmpegPCMAudio(f"{SPEECH_CACHE_DIR}/start.mp3")
        session.voice_client.play(audio)



    # ---------- Stop Recording ----------
    @bot.tree.command(name="stop", description="Stop recording meeting")
    async def stop(interaction: Interaction):
        session = bot.get_session(interaction.guild_id)

        if not session.recording:
            await interaction.response.send_message(
                "No active recording to stop",
                ephemeral=True
            )
            return

        # Defer immediately
        await interaction.response.defer(ephemeral=True)
        
        session.recording = False

        if session.voice_client and session.voice_client.is_listening():
            session.voice_client.stop_listening()

            # Play notification sound
            if session.voice_client.is_playing():
                session.voice_client.stop()
            audio = FFmpegPCMAudio(f"{SPEECH_CACHE_DIR}/stop.mp3")
            session.voice_client.play(audio)

            if session.recorder:
                session.recorder.cleanup()
                
                webhook_url = session.transcription_webhook.url if session.transcription_webhook else None
                spawn_processing(session.recorder.session_dir, webhook_url=webhook_url)
                
                session_dir = session.recorder.session_dir
                session.recorder = None
                
                await interaction.followup.send(
                    f"Recording stopped. Transcription will be sent here when ready. (Session: `{session_dir.name}`)",
                    ephemeral=True
                )
            else:
                await interaction.followup.send("Recording stopped.", ephemeral=True)
        else:
            await interaction.followup.send(
                "Recording was not active on the voice client.",
                ephemeral=True
            )
