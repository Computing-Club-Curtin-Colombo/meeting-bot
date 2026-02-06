import asyncio
import discord
from discord.ext import commands
from bot import MeetingBot
from bot.commands.voice_commands import setup_voice_commands
from bot.commands.tts_commands import setup_tts_commands
from bot.processing.pipeline import spawn_processing
from bot.utils.config import BOT_TOKEN

intents = discord.Intents.all()

bot = MeetingBot(command_prefix="?", intents=intents)


@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user}")
    
# ---------- Auto Leave When Alone ----------
@bot.event
async def on_voice_state_update(member, before, after):
    
    session = bot.get_session(member.guild.id)

    if session.voice_client is None:
        return

    # ---- Bot kicked detection ----
    if member == bot.user and after.channel is None:
        print(f"Bot was disconnected from {member.guild.name}.")
        await stop_recording(member.guild.id)
        return

    # ---- Empty channel detection ----
    channel = session.voice_client.channel
    if channel is None:
        return

    humans = [m for m in channel.members if not m.bot]

    if len(humans) == 0:
        await handle_empty_channel(member.guild.id)


async def stop_recording(guild_id):
    session = bot.get_session(guild_id)
    if not session.recording:
        return

    session.recording = False

    if session.voice_client and session.voice_client.is_listening():
        session.voice_client.stop_listening()
        
    if session.recorder:
        print(f"Cleaning up recorder for guild {guild_id}...")
        session.recorder.cleanup()
        
        webhook_url = session.transcription_webhook.url if session.transcription_webhook else None
        spawn_processing(session.recorder.session_dir, webhook_url=webhook_url)
        session.recorder = None
        

async def handle_empty_channel(guild_id):
    session = bot.get_session(guild_id)
    print(f"Channel in guild {guild_id} empty. Waiting 30 seconds.")

    await asyncio.sleep(30)

    if session.voice_client is None:
        return
    
    channel = session.voice_client.channel
    if channel is None:
        return

    humans = [m for m in channel.members if not m.bot]

    if len(humans) == 0:
        print(f"Still empty in {guild_id}. Leaving.")
        await stop_recording(guild_id)
        await session.voice_client.disconnect()


async def run_bot():
    setup_voice_commands(bot)
    setup_tts_commands(bot)
    
    await bot.start(BOT_TOKEN)
