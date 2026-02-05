import sounddevice as sd
import numpy as np
from faster_whisper import WhisperModel
import queue
import threading
from pathlib import Path
from huggingface_hub import snapshot_download
import os
from dotenv import load_dotenv
import json

# ---------- ENV ----------
load_dotenv()

script_dir = Path(__file__).resolve().parent
hf_cache_dir = script_dir / "hf_cache"
hf_cache_dir.mkdir(parents=True, exist_ok=True)

os.environ["HF_HOME"] = str(hf_cache_dir)

# ---------- MODEL DOWNLOAD ----------
model_path = snapshot_download(
    repo_id="Systran/faster-whisper-small",
    local_dir=str(hf_cache_dir)
)

print("Model ready")

# ---------- LOAD MODEL ----------
model = WhisperModel(
    model_path,
    device="cpu",
    compute_type="int8"
)

session_dir = Path("sessions") / "2026-02-05_23-24-26"

metadata_path = session_dir / "metadata.json"
with open(metadata_path, "r", encoding="utf8") as f:
    metadata = json.load(f)

segments, info = model.transcribe("sessions/2026-02-05_23-24-26/users/1013203339804147762.todolodo_1.wav")

for segment in segments:
    print(segment.start, segment.end, segment.text)