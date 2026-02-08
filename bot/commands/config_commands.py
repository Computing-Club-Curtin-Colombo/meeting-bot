import discord
from discord import Interaction
from bot import MeetingBot
from bot.utils import config
from utils.logger import logger

def setup_config_commands(bot: MeetingBot):
    
    @bot.tree.command(name="config", description="Configure AI model settings")
    @discord.app_commands.describe(
        whisper_model="Transcription model (tiny, base, small, medium, large-v3)",
        whisper_device="Device for Whisper (cuda, cpu)",
        summarizer_model="Large Language Model for meeting summary"
    )
    @discord.app_commands.choices(
        whisper_model=[
            discord.app_commands.Choice(name="tiny", value="tiny"),
            discord.app_commands.Choice(name="base", value="base"),
            discord.app_commands.Choice(name="small", value="small"),
            discord.app_commands.Choice(name="medium", value="medium"),
            discord.app_commands.Choice(name="large-v3", value="large-v3")
        ],
        whisper_device=[
            discord.app_commands.Choice(name="cuda (GPU)", value="cuda"),
            discord.app_commands.Choice(name="cpu", value="cpu")
        ],
        summarizer_model=[
            discord.app_commands.Choice(name="Auto (Logic based)", value="auto"),
            discord.app_commands.Choice(name="Qwen2.5-7B", value="Qwen/Qwen2.5-7B-Instruct"),
            discord.app_commands.Choice(name="Qwen2.5-14B", value="Qwen/Qwen2.5-14B-Instruct"),
            discord.app_commands.Choice(name="LLaMA-3.1-8B", value="meta-llama/Llama-3.1-8B-Instruct")
        ]
    )
    async def configure(
        interaction: Interaction, 
        whisper_model: str = None, 
        whisper_device: str = None,
        summarizer_model: str = None
    ):
        changes = []
        
        if whisper_model:
            config.WHISPER_MODEL = whisper_model
            changes.append(f"Whisper Model -> `{whisper_model}`")
            
        if whisper_device:
            config.DEVICE = whisper_device
            if whisper_device == "cuda":
                config.COMPUTE_TYPE = "float16"
            else:
                config.COMPUTE_TYPE = "int8"
            changes.append(f"Whisper Device -> `{whisper_device}` (Compute: {config.COMPUTE_TYPE})")
            
        if summarizer_model:
            config.LLM_MODEL = summarizer_model
            import bot.processing.summarizer as summarizer
            summarizer.MODEL_ID = summarizer_model
            changes.append(f"Summarizer Model -> `{summarizer_model}`")
            
        if not changes:
            await interaction.response.send_message(
                f"**Current Settings:**\n"
                f"- Whisper Model: `{config.WHISPER_MODEL}`\n"
                f"- Whisper Device: `{config.DEVICE}`\n"
                f"- Summarizer Model: `{config.LLM_MODEL}`",
                ephemeral=True
            )
            return

        logger.info(f"Config updated by {interaction.user}: {', '.join(changes)}")
        await interaction.response.send_message(
            "**Configuration Updated!**\n" + "\n".join(f"- {c}" for c in changes),
            ephemeral=True
        )
