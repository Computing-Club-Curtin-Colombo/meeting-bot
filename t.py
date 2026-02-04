import edge_tts
import asyncio

async def list_voices():
    voices = await edge_tts.list_voices()
    for voice in voices:
        print(f"{voice['ShortName']} | {voice['Gender']} | {voice['Locale']}")

asyncio.run(list_voices())