import discord
from discord.ext import commands
from discord import app_commands
import edge_tts
import asyncio
import wave
import time
from discord.ext import voice_recv
from dotenv import load_dotenv
import os

load_dotenv()

TOKEN = os.environ["BOT_TOKEN"]

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="?", intents=intents)

#app_commands.CommandTree(bot)  # Initialize command tree for slash commands

status = ""
recording = False
voice_client = None
wave_file = None
alone_timer = None


# ---------- Audio Sink ----------
class Recorder(voice_recv.AudioSink):

    def __init__(self):
        super().__init__()
        self.files = {}

    def wants_opus(self):
        return False

    def write(self, user, data):

        if not data.pcm:
            return
        if user.id not in self.files:
            wf = wave.open(f"{user.id}.{user.name}.wav", "wb")
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(48000)
            self.files[user.id] = wf

        self.files[user.id].writeframes(data.pcm)

    def cleanup(self):
        for wf in self.files.values():
            wf.close()


@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user}")


# ---------- Join Command ----------
@bot.tree.command(name="join")
async def join(interaction: discord.Interaction):
    
    global voice_client

    if interaction.user.voice is None:
        await interaction.response.send_message(
            "You must be in a voice channel",
            ephemeral=True
        )
        return

    channel = interaction.user.voice.channel
    voice_client = await channel.connect(cls=voice_recv.VoiceRecvClient)

    await interaction.response.send_message(
        "Joined voice channel",
        ephemeral=True
    )


# ---------- Start Recording ----------
@bot.tree.command(name="record", description="Start recording meeting")
async def record(interaction: discord.Interaction):
    
    global recording, voice_client
    
    if voice_client is None:
        await interaction.response.send_message(
            "Bot not in voice channel!",
            ephemeral=True
        )
        return

    voice_client.listen(Recorder())
    recording = True
    await interaction.response.send_message(
        "Recording started",
        ephemeral=True   # ← ONLY user sees this
    )



# ---------- Stop Recording ----------
@bot.tree.command(name="stop", description="Stop recording meeting")
async def stop(interaction: discord.Interaction):
    await stop_recording(interaction)
    
async def stop_recording(interaction: discord.Interaction):

    global recording, voice_client

    recording = False

    if voice_client and voice_client.is_listening():
        voice_client.stop_listening()

    if interaction:
        await interaction.response.send_message(
            "Recording stopped",
            ephemeral=True
        )

# ---------- SAY COMMAND ----------
@bot.tree.command(name="say", description="Bot speaks text")
@app_commands.describe(text="Text for bot to speak")
async def say(interaction: discord.Interaction, text: str):

    global voice_client

    if voice_client is None:
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
    communicate = edge_tts.Communicate(text, "en-AU-WilliamMultilingualNeural")
    await communicate.save("speech.mp3")

    # Stop if already speaking
    if voice_client.is_playing():
        voice_client.stop()

    # Play audio using FFmpeg
    audio = discord.FFmpegPCMAudio("speech.mp3")
    voice_client.play(audio)


# ---------- Auto Leave When Alone ----------
@bot.event
async def on_voice_state_update(member, before, after):

    global voice_client

    if voice_client is None:
        return

    # ---- Bot kicked detection ----
    if member == bot.user and after.channel is None:
        print("Bot was disconnected.")
        await stop_recording()
        return

    # ---- Empty channel detection ----
    channel = voice_client.channel
    if channel is None:
        return

    humans = [m for m in channel.members if not m.bot]

    if len(humans) == 0:
        await handle_empty_channel()



async def handle_empty_channel():

    global voice_client

    print("Channel empty. Waiting 30 seconds.")

    await asyncio.sleep(30)

    if voice_client is None:
        return

    channel = voice_client.channel
    humans = [m for m in channel.members if not m.bot]

    if len(humans) == 0:
        print("Still empty. Leaving.")
        await voice_client.disconnect()


bot.run(TOKEN)
