from bot import MeetingBot
from discord import Interaction
from pathlib import Path
import json
from datetime import datetime
from utils.logger import logger


def setup_session_commands(bot: MeetingBot):
    
    # ---------- Sessions Command ----------
    @bot.tree.command(name="sessions", description="List all recording sessions")
    async def sessions(
        interaction: Interaction,
        verbose: bool = False,
        show_all: bool = False
    ):
        logger.info(f"Listing sessions (verbose={verbose}, show_all={show_all}) | Requested by {interaction.user}")
        await interaction.response.defer(ephemeral=True)
        
        sessions_dir = Path("sessions")
        
        if not sessions_dir.exists():
            await interaction.followup.send(
                "No sessions directory found.",
                ephemeral=True
            )
            return
        
        # Get all session directories
        session_folders = sorted(
            [d for d in sessions_dir.iterdir() if d.is_dir()],
            key=lambda x: x.name,
            reverse=True  # Most recent first
        )
        
        if not session_folders:
            await interaction.followup.send(
                "No sessions found.",
                ephemeral=True
            )
            return
        
        # Build response
        lines = [f"**Found {len(session_folders)} session(s)**\n"]
        
        for session_dir in session_folders:
            metadata_path = session_dir / "metadata.json"
            
            # Check if metadata exists
            if not metadata_path.exists():
                if show_all:
                    lines.append(f"🔴 **[CORRUPTED]** `{session_dir.name}`")
                continue
            
            try:
                with open(metadata_path, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
                
                # Parse session start time
                session_start = metadata.get("session_start", "Unknown")
                try:
                    dt = datetime.fromisoformat(session_start)
                    formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    formatted_time = session_start
                
                # Basic info
                channel_info = metadata.get("channel", {})
                channel_name = channel_info.get("name", "Unknown")
                user_count = len(metadata.get("users", {}))
                
                if verbose:
                    # Detailed listing
                    lines.append(f"\n📁 **Session:** `{session_dir.name}`")
                    lines.append(f"   ⏰ **Time:** {formatted_time}")
                    lines.append(f"   🔊 **Channel:** {channel_name}")
                    
                    # Category info
                    category_name = channel_info.get("category_name")
                    if category_name:
                        lines.append(f"   📂 **Category:** {category_name}")
                    
                    # Users
                    users = metadata.get("users", {})
                    if users:
                        lines.append(f"   👥 **Participants ({user_count}):**")
                        for user_id, user_data in users.items():
                            user_name = user_data.get("name", "Unknown")
                            lines.append(f"      • {user_name}")
                    
                    # Check for transcript
                    transcript_path = session_dir / "transcript.txt"
                    if transcript_path.exists():
                        lines.append(f"   ✅ **Transcript:** Available")
                    else:
                        lines.append(f"   ⏳ **Transcript:** Processing/Not available")
                else:
                    # Compact listing
                    lines.append(
                        f"📁 `{session_dir.name}` - {formatted_time} - "
                        f"#{channel_name} - {user_count} participant(s)"
                    )
                    
            except Exception as e:
                if show_all:
                    lines.append(f"⚠️ **[ERROR]** `{session_dir.name}` - {str(e)}")
        
        # Discord has a 2000 character limit per message
        response = "\n".join(lines)
        
        if len(response) > 1900:
            # Split into multiple messages
            chunks = []
            current_chunk = ""
            
            for line in lines:
                if len(current_chunk) + len(line) + 1 > 1900:
                    chunks.append(current_chunk)
                    current_chunk = line + "\n"
                else:
                    current_chunk += line + "\n"
            
            if current_chunk:
                chunks.append(current_chunk)
            
            # Send first chunk as followup
            await interaction.followup.send(chunks[0], ephemeral=True)
            
            # Send remaining chunks
            for chunk in chunks[1:]:
                await interaction.channel.send(chunk)
        else:
            await interaction.followup.send(response, ephemeral=True)
