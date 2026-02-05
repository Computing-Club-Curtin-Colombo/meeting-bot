from faster_whisper import WhisperModel

def run_transcription(session_dir):

    model = WhisperModel(
        "medium",
        device="cuda",
        compute_type="float16"
    )

    # Process user audio files
