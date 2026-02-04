import queue
import discord
from discord.ext import commands
from discord import app_commands
import edge_tts
import asyncio
import wave
import time
# from langdetect import detect
from discord.ext import voice_recv
from dotenv import load_dotenv
import json
from datetime import datetime
from pathlib import Path
import os
import random
import threading

load_dotenv()

TOKEN = os.environ["BOT_TOKEN"]

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="?", intents=intents)

#app_commands.CommandTree(bot)  # Initialize command tree for slash commands

voices = asyncio.run(edge_tts.list_voices())
status = ""
recording = False
voice_client = None
wave_file = None
alone_timer = None


# ---------- Audio Sink ----------
class Recorder(voice_recv.AudioSink):

    def __init__(self):
        super().__init__()

        # ----- Session Folder -----
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.session_dir = Path("sessions") / timestamp
        self.users_dir = self.session_dir / "users"

        self.users_dir.mkdir(parents=True, exist_ok=True)

        # ----- Track state -----
        self.files = {}
        self.queues = {}
        self.threads = {}
        self.running = True
        
        self.join_offsets = {}
        self.start_time = time.time()

        # Metadata
        self.metadata = {
            "session_start": timestamp,
            "users": {}
        }

    def wants_opus(self):
        return False

    # ----- Get session elapsed ms -----
    def current_offset_ms(self):
        return int((time.time() - self.start_time) * 1000)
    
    # ---------- Worker Thread ----------
    def user_worker(self, user_id):

        wf = self.files[user_id]
        q = self.queues[user_id]

        while self.running or not q.empty():
            try:
                data = q.get(timeout=0.5)
                wf.writeframes(data)
            except queue.Empty:
                continue

    # ---------- Add User ----------
    def add_user(self, user):

        filepath = self.users_dir / f"{user.id}.{user.name}.wav"

        wf = wave.open(str(filepath), "wb")
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(48000)

        self.files[user.id] = wf
        self.queues[user.id] = queue.Queue()

        # Metadata
        offset = self.current_offset_ms()
        self.join_offsets[user.id] = offset

        self.metadata["users"][str(user.id)] = {
            "name": user.name,
            "join_offset_ms": offset
        }

        # Start worker thread
        thread = threading.Thread(
            target=self.user_worker,
            args=(user.id,),
            daemon=True
        )
        thread.start()

        self.threads[user.id] = thread

    # ---------- Write Audio ----------
    def write(self, user, data):

        if not data.pcm:
            return

        # Add new user dynamically
        if user.id not in self.files:
            self.add_user(user)

        packet_size = len(data.pcm)
        silence = bytes(packet_size)

        # Push audio to queues
        for uid in self.files.keys():

            if uid == user.id:
                self.queues[uid].put(data.pcm)
            else:
                self.queues[uid].put(silence)

    # ---------- Cleanup ----------
    def cleanup(self):

        self.running = False

        # Wait for workers
        for thread in self.threads.values():
            thread.join()

        # Close files
        for wf in self.files.values():
            wf.close()

        # Save metadata
        meta_path = self.session_dir / "metadata.json"
        with open(meta_path, "w", encoding="utf8") as f:
            json.dump(self.metadata, f, indent=4)


# ---------- Bot Events ----------
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
    communicate = edge_tts.Communicate(text, random.choice(voices)["ShortName"])
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
