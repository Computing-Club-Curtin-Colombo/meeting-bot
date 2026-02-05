import multiprocessing
from bot.processing.transcriber import run_transcription

def spawn_processing(session_dir):
    p = multiprocessing.Process(
        target=run_transcription,
        args=(session_dir,)
    )
    p.start()
