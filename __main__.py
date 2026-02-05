from bot.client import run_bot
from bot.utils.file_utils import generate_prepared_speech_files
import asyncio

if __name__ == "__main__":
    asyncio.run(generate_prepared_speech_files())
    run_bot()
