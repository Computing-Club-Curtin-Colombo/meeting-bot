import sqlite3
import json
from pathlib import Path
from datetime import datetime, timedelta
from utils.logger import logger

def generate_prompt(session_dir):
    session_path = Path(session_dir)
    metadata_path = session_path / "metadata.json"
    db_path = session_path / "meeting.db"
    output_path = session_path / "PROMPT1"

    if not metadata_path.exists():
        return f"Metadata not found at {metadata_path}"

    with open(metadata_path, "r", encoding="utf8") as f:
        metadata = json.load(f)

    if not db_path.exists():
        logger.warning(f"Meeting database not found at {db_path}")
        return None

    # Load Users from Database
    user_map = {}
    participants = []
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, user_name, nick_name FROM users WHERE is_bot = 0")
        for uid, user_name, nick_name in cursor:
            display_name = nick_name or user_name
            user_map[uid] = display_name
            participants.append(display_name)
        conn.close()
    except Exception as e:
        logger.error(f"Error loading users from database: {e}")

    session_start = datetime.fromisoformat(metadata.get("session_start"))
    date_str = session_start.strftime("%Y-%m-%d")
    title = metadata.get("title")
    
    # --- System Prompt ---
    prompt = [
        "SYSTEM:",
        "You extract factual meeting data. Do not summarize. Do not infer.",
        "Output ONLY valid JSON that strictly follows the schema below.",
        "",
        "JSON Schema:",
        "{",
        '  "attendees": [],',
        '  "events": [],',
        '  "agenda_items": [],',
        '  "key_statements": [],',
        '  "decisions": [],',
        '  "action_items": [',
        "    {",
        '      "person": "",',
        '      "task": "",',
        '      "deadline": null',
        "    }",
        "  ]",
        "}",
        "",
        "[MEETING METADATA]",
        f"Date: {date_str}"
    ]
    
    if title:
        prompt.append(f"Title: {title}")
        
    prompt.extend([
        "Platform: Discord",
        "",
        "[PARTICIPANTS]",
        "\n".join(participants),
        ""
    ])

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # --- Event Log ---
        prompt.append("[EVENT LOG]")
        cursor.execute("""
            SELECT timestamp, user_id, 
                   before_channel_id, after_channel_id,
                   before_self_mute, after_self_mute,
                   before_self_deaf, after_self_deaf
            FROM events 
            ORDER BY timestamp ASC
        """)
        
        for row in cursor:
            ts_str, uid, b_cid, a_cid, b_mute, a_mute, b_deaf, a_deaf = row
            name = user_map.get(uid, f"User({uid})")
            dt = datetime.fromisoformat(ts_str)
            time_str = dt.strftime("%H:%M:%S")
            
            event_type = None
            if b_cid is None and a_cid is not None:
                event_type = "joined"
            elif b_cid is not None and a_cid is None:
                event_type = "left"
            elif not b_mute and a_mute:
                event_type = "muted"
            elif b_mute and not a_mute:
                event_type = "unmuted"
            elif not b_deaf and a_deaf:
                event_type = "deafened"
            elif b_deaf and not a_deaf:
                event_type = "undeafened"
            
            if event_type:
                prompt.append(f"{time_str} {name} {event_type}")
        prompt.append("")

        # --- Chat Notes ---
        prompt.append("[CHAT NOTES]")
        cursor.execute("SELECT timestamp, user_id, content FROM notes ORDER BY timestamp ASC")
        for ts_str, uid, content in cursor:
            name = user_map.get(uid, f"User({uid})")
            dt = datetime.fromisoformat(ts_str)
            time_str = dt.strftime("%H:%M:%S")
            prompt.append(f"{time_str} {name}: {content}")
        prompt.append("")

        # --- Transcript ---
        prompt.append("[TRANSCRIPT]")
        cursor.execute("SELECT timestamp, user_id, text FROM transcriptions ORDER BY timestamp ASC")
        for ts_str, uid, text in cursor:
            name = user_map.get(uid, f"User({uid})")
            dt = datetime.fromisoformat(ts_str)
            time_str = dt.strftime("%H:%M:%S")
            prompt.append(f"{time_str} {name}: {text}")
        
        conn.close()
    except Exception as e:
        logger.error(f"Error reading meeting database: {e}")
    
    # Save to file
    final_output = "\n".join(prompt)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(final_output)
    
    logger.info(f"PROMPT1 file created successfully at {output_path}")
    return final_output

def generate_prompt_2(session_dir):
    session_path = Path(session_dir)
    json_path = session_path / "extracted_data.json"
    output_path = session_path / "PROMPT2"
    
    if not json_path.exists():
        logger.warning(f"extracted_data.json not found at {json_path}. Cannot generate PROMPT2.")
        return None
        
    try:
        with open(json_path, "r", encoding="utf8") as f:
            extracted_data = json.load(f)
            
        prompt = [
            "SYSTEM:",
            "You are a professional meeting assistant. Based on the provided meeting data in JSON format, ",
            "generate a high-quality, professional meeting minutes report in Markdown.",
            "The report should include:",
            "1. Meeting Overview (Title, Date, Participants)",
            "2. Detailed Discussion Summary",
            "3. Decisions Made",
            "4. Action Items (with Owners and Deadlines)",
            "5. Key Highlights and Statements",
            "",
            "Maintain a formal and clear tone. Use bullet points and headers for readability.",
            "",
            "[EXTRACTED DATA]",
            json.dumps(extracted_data, indent=2),
            ""
        ]
        
        final_output = "\n".join(prompt)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(final_output)
            
        logger.info(f"PROMPT2 file created successfully at {output_path}")
        return final_output
    except Exception as e:
        logger.error(f"Failed to generate PROMPT2: {e}")
        return None

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        generate_prompt(sys.argv[1])
