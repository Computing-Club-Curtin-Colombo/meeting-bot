import threading
import queue
from time import time
import wave

from bot.utils.file_utils import safe_close_wav

class UserTrack:

    def __init__(self, filepath):
        self.queue = queue.Queue()
        self.running = True

        self.wav = wave.open(str(filepath), "wb")
        self.wav.setnchannels(2)
        self.wav.setsampwidth(2)
        self.wav.setframerate(48000)
        
        self.last_packet_time = time()

        self.thread = threading.Thread(target=self.worker, daemon=True)
        self.thread.start()

    def enqueue(self, pcm):
        now = time()
        gap = now - self.last_packet_time
        
        # Calculate missing frames (20ms per frame)
        # Cap silence at 30 seconds (1500 frames) to prevent OOM/Disk-fill if clock jumps
        missing_frames = min(int(gap / 0.02), 1500)
        
        if missing_frames > 1:
            silence = bytes(len(pcm))
            for _ in range(missing_frames - 1):
                self.queue.put(silence)
        
        self.queue.put(pcm)
        self.last_packet_time = now

    def worker(self):
        while self.running or not self.queue.empty():
            try:
                pcm = self.queue.get(timeout=0.1)
                self.wav.writeframes(pcm)
            except queue.Empty:
                continue

    def stop(self):
        self.running = False
        self.thread.join()
        safe_close_wav(self.wav)
