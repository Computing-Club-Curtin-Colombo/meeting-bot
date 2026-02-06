def spawn_processing(session_dir, webhook_url=None):
    p = multiprocessing.Process(
        target=run_transcription,
        args=(session_dir, webhook_url)
    )
    p.start()
