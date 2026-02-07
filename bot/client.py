import asyncio
import discord
from discord.ext import commands
from bot import MeetingBot
from bot.commands.voice_commands import setup_voice_commands
from bot.commands.tts_commands import setup_tts_commands
from bot.commands.session_commands import setup_session_commands
from bot.processing.pipeline import spawn_processing
from bot.utils.config import BOT_TOKEN

bot = MeetingBot(command_prefix="?", intents=discord.Intents.all())


@bot.event
async def on_ready():
    print(f"Syncing commands...")
    synced = await bot.tree.sync()
    print(f"Synced {len(synced)} command(s): {[cmd.name for cmd in synced]}")
    print(f"Logged in as {bot.user}")
    
# ---------- Auto Leave When Alone ----------
@bot.event
async def on_voice_state_update(member, before, after):
    # Log events if recording is active
    if bot.recording and bot.recorder:
        # Check if the event is relevant to our recording (either before or after was our channel)
        our_channel = bot.voice_client.channel if bot.voice_client else None
        if our_channel and (before.channel == our_channel or after.channel == our_channel):
            bot.recorder.log_event(member, before, after)

    if bot.voice_client is None:
        return

    # Only care about updates in OUR channel
    our_channel = bot.voice_client.channel
    if before.channel != our_channel and after.channel != our_channel:
        return

    # ---- Bot kicked detection ----
    if member == bot.user and after.channel is None:
        print("Bot was disconnected.")
        await stop_recording()
        return

    # ---- Empty channel detection ----
    humans = [m for m in our_channel.members if not m.bot]

    if len(humans) == 0:
        # Avoid starting multiple timers
        if not hasattr(bot, 'leave_timer') or bot.leave_timer is None:
            bot.leave_timer = asyncio.create_task(handle_empty_channel())
            print(f"Leave timer started (30s) for {our_channel.name}")
    else:
        # Someone is back, cancel the timer if it exists
        if hasattr(bot, 'leave_timer') and bot.leave_timer is not None:
            bot.leave_timer.cancel()
            bot.leave_timer = None
            print(f"Channel {our_channel.name} no longer empty. Leave timer cancelled.")


async def stop_recording():
    if not bot.recording:
        return

    print("Stopping recording from client...")
    bot.recording = False

    if bot.voice_client and bot.voice_client.is_listening():
        bot.voice_client.stop_listening()
        
    if bot.recorder:
        # First, ensure the recorder saves its metadata
        bot.recorder.cleanup()
        
        # Then spawn processing with ALL required arguments
        from bot.utils import config
        spawn_processing(
            bot.recorder.session_dir, 
            config.WHISPER_MODEL, 
            config.DEVICE, 
            config.COMPUTE_TYPE, 
            config.HF_CACHE_DIR
        )
        

async def handle_empty_channel():
    try:
        await asyncio.sleep(30)
        
        if bot.voice_client is None:
            return

        channel = bot.voice_client.channel
        if channel is None:
            return

        humans = [m for m in channel.members if not m.bot]

        if len(humans) == 0:
            print(f"Still empty after 30s. Leaving {channel.name}.")
            await stop_recording()
            await bot.voice_client.disconnect()
    except asyncio.CancelledError:
        pass
    finally:
        bot.leave_timer = None


async def run_bot():
    setup_voice_commands(bot)
    setup_tts_commands(bot)
    setup_session_commands(bot)
    
    # Add cleanup handler
    @bot.event
    async def on_close():
        print("Bot shutting down...")
        
        # Stop recording if active
        if bot.recording:
            await stop_recording()
        
        # Disconnect from voice
        if bot.voice_client:
            await bot.voice_client.disconnect()
    
    await bot.start(BOT_TOKEN)
