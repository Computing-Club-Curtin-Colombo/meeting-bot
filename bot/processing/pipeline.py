import multiprocessing
from bot.processing.transcriber import run_transcription

# Track active processes
_active_processes = []

def spawn_processing(session_dir, whisper_model, device, compute_type, hf_cache_dir):
    """Spawn a transcription process and track it"""
    p = multiprocessing.Process(
        target=run_transcription,
        args=(session_dir, whisper_model, device, compute_type, hf_cache_dir)
    )
    p.start()
    _active_processes.append(p)
    
    # Clean up finished processes
    _cleanup_finished_processes()

def _cleanup_finished_processes():
    """Remove finished processes from tracking list"""
    global _active_processes
    _active_processes = [p for p in _active_processes if p.is_alive()]

def terminate_all_processes():
    """Terminate all active transcription processes"""
    print(f"Terminating {len(_active_processes)} active transcription process(es)...")
    for p in _active_processes:
        if p.is_alive():
            p.terminate()
            p.join(timeout=2)  # Wait up to 2 seconds
            if p.is_alive():
                p.kill()  # Force kill if still running
    _active_processes.clear()
