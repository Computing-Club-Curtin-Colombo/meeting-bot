import multiprocessing
from bot.processing.transcriber import run_transcription

def spawn_processing(session_dir, whisper_model, device, compute_type, hf_cache_dir):
    p = multiprocessing.Process(
        target=run_transcription,
        args=(session_dir, whisper_model, device, compute_type, hf_cache_dir)
    )
    p.start()
