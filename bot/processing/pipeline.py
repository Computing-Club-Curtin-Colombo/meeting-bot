import multiprocessing
import bot.utils.config as config
from bot.processing.transcriber import run_transcription

def spawn_processing(session_dir, webhook_url=None):
    # Capture current config to pass to the new process (Windows multiprocessing sync)
    process_config = {
        "model": config.WHISPER_MODEL,
        "device": config.DEVICE,
        "compute": config.COMPUTE_TYPE,
        "cache": config.HF_CACHE_DIR
    }
    
    p = multiprocessing.Process(
        target=run_transcription,
        args=(session_dir, webhook_url, process_config)
    )
    p.start()
