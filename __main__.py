import argparse
import os
import sys
import asyncio
import platform
import subprocess
from pathlib import Path

# Try to import dependencies, or provide a way to install them
try:
    from dotenv import load_dotenv
except ImportError:
    print("Installing missing dependency: python-dotenv")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "python-dotenv"])
    from dotenv import load_dotenv

try:
    import discord
    from discord.ext import voice_recv
except ImportError:
    print("Installing missing dependency: discord.py")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "discord.py", "discord-ext-voice-recv"])
    import discord
    from discord.ext import voice_recv

try:
    import psutil
except ImportError:
    print("Installing missing dependency: psutil")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "psutil"])
    import psutil

try:
    import numpy
except ImportError:
    print("Installing missing dependency: numpy")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "numpy"])
    import numpy

try:
    from faster_whisper import WhisperModel
    import ctranslate2
except ImportError:
    print("Installing missing dependency: faster-whisper")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "faster-whisper"])
    from faster_whisper import WhisperModel
    import ctranslate2

import bot.utils.config as config
from bot.client import run_bot
from bot.utils.file_utils import generate_prepared_speech_files

def get_system_info():
    """Detects CPU RAM and GPU VRAM if available."""
    info = {
        "ram_gb": psutil.virtual_memory().total / (1024**3),
        "gpu_available": False,
        "vram_gb": 0,
        "cuda_version": None
    }
    
    # Check CUDA availability via ctranslate2
    try:
        if ctranslate2.get_cuda_device_count() > 0:
            info["gpu_available"] = True
            # Note: ctranslate2 doesn't give VRAM easily, normally we'd use nvidia-smi or torch
            # We'll use a fallback check for VRAM if we really need it, but for now we assume 
            # if CUDA is there, we can try at least 'medium'
            info["vram_gb"] = 4 # Default assumption if CUDA exists
    except:
        pass
        
    return info

def select_best_model(info):
    """Selects the best whisper model based on hardware."""
    if info["gpu_available"]:
        if info["vram_gb"] >= 8:
            return "large-v3", "cuda", "float16"
        elif info["vram_gb"] >= 4:
            return "medium", "cuda", "float16"
        else:
            return "small", "cuda", "int8_float16"
    else:
        # CPU path
        if info["ram_gb"] >= 16:
            return "medium", "cpu", "int8"
        elif info["ram_gb"] >= 8:
            return "small", "cpu", "int8"
        else:
            return "base", "cpu", "int8"

def setup_cuda_env(cuda_path=None):
    """Sets up CUDA environment variables."""
    if cuda_path:
        cuda_path = Path(cuda_path)
        if cuda_path.exists():
            print(f"Adding {cuda_path} to PATH and CUDA_PATH")
            os.environ["CUDA_PATH"] = str(cuda_path)
            os.environ["PATH"] = str(cuda_path / "bin") + os.pathsep + os.environ["PATH"]
        else:
            print(f"Warning: Provided CUDA path {cuda_path} does not exist.")

async def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="Meeting Bot Standalone Entry")
    parser.add_argument("--cpu", action="store_true", help="Force CPU mode")
    parser.add_argument("--gpu", action="store_true", help="Force GPU (CUDA) mode")
    parser.add_argument("--model", type=str, help="Specific Whisper model to use (e.g., base, small, medium, large-v3)")
    parser.add_argument("--cuda-path", type=str, help="Path to CUDA toolkit installation")
    parser.add_argument("--cache-dir", type=str, help="Custom directory for huggingface cache")
    
    args = parser.parse_args()
    
    # 1. Setup Cache
    if args.cache_dir:
        config.HF_CACHE_DIR = args.cache_dir
    os.makedirs(config.HF_CACHE_DIR, exist_ok=True)
    os.environ["HF_HOME"] = config.HF_CACHE_DIR

    # 2. Setup CUDA Env
    setup_cuda_env(args.cuda_path)

    # 3. Hardware Detection
    sys_info = get_system_info()
    print(f"System Info: RAM={sys_info['ram_gb']:.1f}GB, GPU_Available={sys_info['gpu_available']}")

    # 4. Resolve Device and Model
    if args.cpu:
        device = "cpu"
    elif args.gpu:
        device = "cuda"
        # Check for NVIDIA drivers
        try:
            subprocess.check_output(["nvidia-smi"])
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("ERROR: '--gpu' flag was given, but NVIDIA drivers or 'nvidia-smi' were not found.")
            print("Please install the latest NVIDIA drivers: https://www.nvidia.com/Download/index.aspx")
            sys.exit(1)
            
        if not sys_info["gpu_available"]:
            print("ERROR: GPU mode requested. Drivers found, but CUDA is not accessible by ctranslate2.")
            print("You may need to install the CUDA Toolkit or ensure cuBLAS/cuDNN DLLs are in your PATH.")
            print(f"Current PATH: {os.environ['PATH'][:200]}...")
            sys.exit(1)
    else:
        device = "cuda" if sys_info["gpu_available"] else "cpu"

    # 5. Model Selection Logic
    best_model, auto_device, compute_type = select_best_model(sys_info)
    
    config.DEVICE = device
    config.WHISPER_MODEL = args.model if args.model else best_model
    config.COMPUTE_TYPE = compute_type if device == "cuda" else "int8"

    print(f"--- Configuration ---")
    print(f"Device: {config.DEVICE}")
    print(f"Model: {config.WHISPER_MODEL}")
    print(f"Compute: {config.COMPUTE_TYPE}")
    print(f"Cache: {config.HF_CACHE_DIR}")
    print(f"---------------------")

    # 6. Pre-flight checks (Prepared speech files)
    print("Generating pre-cached speech files...")
    await generate_prepared_speech_files()

    # 7. Start Bot
    print("Starting bot...")
    await run_bot()

if __name__ == "__main__":
    import signal
    
    # Store the bot instance for cleanup
    bot_instance = None
    
    def signal_handler(sig, frame):
        """Handle Ctrl+C gracefully"""
        print("\n\nShutting down gracefully...")
        if bot_instance:
            # Create new event loop for cleanup if needed
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(bot_instance.close())
                else:
                    loop.run_until_complete(bot_instance.close())
            except:
                pass
        sys.exit(0)
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Import bot after signal handlers are set
        from bot.client import bot
        bot_instance = bot
        
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot stopped by user.")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
