import edge_tts
from langdetect import detect

class TTSEngine:

    async def generate(self, text, output_file):

        lang = detect(text)

        voice_map = {
            "en": "en-AU-WilliamMultilingualNeural",
            "si": "si-LK-SameeraNeural",
            "ta": "ta-IN-ValluvarNeural"
        }

        voice = voice_map.get(lang, voice_map["en"])

        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_file)
