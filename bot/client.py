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
    
    print(f"Voice state update: {member} | Before: {before.channel} | After: {after.channel}")

    if bot.voice_client is None:
        return

    # ---- Bot kicked detection ----
    if member == bot.user and after.channel is None:
        print("Bot was disconnected.")
        await stop_recording()
        return

    # ---- Empty channel detection ----
    channel = bot.voice_client.channel
    if channel is None:
        return

    humans = [m for m in channel.members if not m.bot]

    if len(humans) == 0:
        await handle_empty_channel()


async def stop_recording():


    bot.recording = False

    if bot.voice_client and bot.voice_client.is_listening():
        bot.voice_client.stop_listening()
        
        if bot.recorder:
            spawn_processing(bot.recorder.session_dir)
        

async def handle_empty_channel():

    print("Channel empty. Waiting 30 seconds.")

    await asyncio.sleep(30)

    if bot.voice_client is None:
        return
    
    

    channel = bot.voice_client.channel
    humans = [m for m in channel.members if not m.bot]

    if len(humans) == 0:
        print("Still empty. Leaving.")
        if bot.recording:
            stop_recording()
            print("Stopped recording.")
        await bot.voice_client.disconnect()


async def run_bot():
    setup_voice_commands(bot)
    setup_tts_commands(bot)
    
    # Add cleanup handler
    @bot.event
    async def on_close():
        print("Bot shutting down...")
        
        # Stop recording if active
        if bot.recording and bot.voice_client and bot.voice_client.is_listening():
            bot.voice_client.stop_listening()
            
            # Save recorder data
            if bot.recorder:
                bot.recorder.cleanup()
                spawn_processing(bot.recorder.session_dir)
        
        # Disconnect from voice
        if bot.voice_client:
            await bot.voice_client.disconnect()
    
    await bot.start(BOT_TOKEN)
