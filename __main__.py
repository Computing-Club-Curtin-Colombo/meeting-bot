"""Meeting Bot - Discord voice recording and transcription bot"""
import asyncio
import os
from dotenv import load_dotenv

import bot.utils.config as config
from bot.client import run_bot, bot
from bot.utils.file_utils import generate_prepared_speech_files
from utils.dependencies import install_all_dependencies
from utils.args import parse_arguments
from utils.hardware import (
    get_system_info,
    select_best_model,
    setup_cuda_env,
    verify_gpu_availability
)
from utils.shutdown import setup_signal_handlers
from utils.logger import logger


async def main():
    """Main entry point for the bot"""
    load_dotenv()
    
    # Parse command-line arguments
    args = parse_arguments()
    
    # 1. Setup Cache
    if args.cache_dir:
        config.HF_CACHE_DIR = args.cache_dir
    os.makedirs(config.HF_CACHE_DIR, exist_ok=True)
    os.environ["HF_HOME"] = config.HF_CACHE_DIR

    # 2. Setup CUDA Environment
    setup_cuda_env(args.cuda_path)

    # 3. Hardware Detection
    sys_info = get_system_info()
    
    # Use the logger to show system and hardware info in the requested color format
    logger.info(f"System: {sys_info['os']} | Python: {sys_info['python']}")
    logger.info(f"Hardware: RAM={sys_info['ram_gb']:.1f}GB | GPU Available: {sys_info['gpu_available']}")

    # 4. Resolve Device and Model
    if args.cpu:
        device = "cpu"
    elif args.gpu:
        device = "cuda"
        verify_gpu_availability(sys_info)
    else:
        device = "cuda" if sys_info["gpu_available"] else "cpu"

    # 5. Model Selection Logic
    best_model, auto_device, compute_type = select_best_model(sys_info)
    
    config.DEVICE = device
    config.WHISPER_MODEL = args.model if args.model else best_model
    config.COMPUTE_TYPE = compute_type if device == "cuda" else "int8"

    logger.info("Configuration set:")
    logger.info(f"  > Device:  {config.DEVICE}")
    logger.info(f"  > Model:   {config.WHISPER_MODEL}")
    logger.info(f"  > Compute: {config.COMPUTE_TYPE}")
    logger.info(f"  > Cache:   {config.HF_CACHE_DIR}")

    # 6. Pre-flight checks (Prepared speech files)
    logger.debug("Generating pre-cached speech files...")
    await generate_prepared_speech_files()

    # 7. Start Bot
    logger.info("Initiating bot main loop...")
    await run_bot()


if __name__ == "__main__":
    # Install dependencies first
    install_all_dependencies()
    
    # Setup signal handlers for graceful shutdown
    setup_signal_handlers(bot)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.warning("Bot stopped by user (KeyboardInterrupt).")
    except Exception as e:
        logger.critical(f"FATAL ERROR: {e}")
        import traceback
        logger.error(traceback.format_exc())
