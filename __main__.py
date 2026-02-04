import sounddevice as sd
import numpy as np
from faster_whisper import WhisperModel
import queue
import threading
from pathlib import Path
from huggingface_hub import snapshot_download
import os
from dotenv import load_dotenv

# ---------- ENV ----------
load_dotenv()

script_dir = Path(__file__).resolve().parent
hf_cache_dir = script_dir / "hf_cache"
hf_cache_dir.mkdir(parents=True, exist_ok=True)

os.environ["HF_HOME"] = str(hf_cache_dir)

# ---------- MODEL DOWNLOAD ----------
model_path = snapshot_download(
    repo_id="Systran/faster-whisper-base",
    local_dir=str(hf_cache_dir)
)

print("Model ready")

# ---------- LOAD MODEL ----------
model = WhisperModel(
    model_path,
    device="cpu",
    compute_type="int8"
)

# Warmup run (reduces first inference delay)
model.transcribe(np.zeros(16000, dtype=np.float32))

# ---------- AUDIO CONFIG ----------
samplerate = 16000
block_duration = 3
silence_threshold = 0.01

audio_queue = queue.Queue()

# ---------- AUDIO CALLBACK ----------
def audio_callback(indata, frames, time, status):
    if status:
        print("Audio status:", status)

    audio_queue.put(indata.copy())

# ---------- TRANSCRIPTION WORKER ----------
def transcribe_worker():
    while True:
        try:
            audio_data = audio_queue.get(timeout=1)

            # Convert int16 → float32 safely
            audio_data = audio_data.astype(np.float32) / 32768.0
            audio_data = audio_data.flatten()

            # Silence detection
            if np.max(np.abs(audio_data)) < silence_threshold:
                continue

            segments, info = model.transcribe(
                audio_data,
                language="en",     # disable auto-detection
                vad_filter=True
            )

            for segment in segments:
                print(segment.text.strip())

        except queue.Empty:
            continue
        except Exception as e:
            print("Worker error:", e)

# ---------- START WORKER ----------
threading.Thread(target=transcribe_worker, daemon=True).start()

# ---------- START MICROPHONE ----------
with sd.InputStream(
    samplerate=samplerate,
    channels=1,
    dtype="int16",
    blocksize=int(samplerate * block_duration),
    callback=audio_callback
):
    print("Listening...")
    while True:
        sd.sleep(1000)
