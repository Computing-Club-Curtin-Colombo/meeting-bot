import os
import sqlite3
import json
from pathlib import Path
from datetime import datetime, timedelta

def generate_prompt(session_dir):
    session_path = Path(session_dir)
    metadata_path = session_path / "metadata.json"
    events_db_path = session_path / "events.db"
    transcripts_db_path = session_path / "transcriptions.db"
    output_path = session_path / "PROMPT1"

    if not metadata_path.exists():
        return f"Metadata not found at {metadata_path}"

    with open(metadata_path, "r", encoding="utf8") as f:
        metadata = json.load(f)

    session_start = datetime.fromisoformat(metadata.get("session_start"))
    date_str = session_start.strftime("%Y-%m-%d")
    
    participants = [user["name"] for user in metadata.get("users", {}).values()]

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
        f"Date: {date_str}",
        "Platform: Discord",
        "",
        "[PARTICIPANTS]",
        "\n".join(participants),
        ""
    ]

    # --- Event Log ---
    prompt.append("[EVENT LOG]")
    if events_db_path.exists():
        try:
            conn = sqlite3.connect(events_db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT timestamp, user_name, 
                       before_channel_id, after_channel_id,
                       before_self_mute, after_self_mute,
                       before_self_deaf, after_self_deaf
                FROM events 
                ORDER BY timestamp ASC
            """)
            
            for row in cursor:
                ts_str, name, b_cid, a_cid, b_mute, a_mute, b_deaf, a_deaf = row
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
            
            conn.close()
        except Exception as e:
             prompt.append(f"Error reading events: {e}")
    prompt.append("")

    # --- Chat Notes ---
    prompt.append("[CHAT NOTES]")
    if events_db_path.exists():
        try:
            conn = sqlite3.connect(events_db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT timestamp, user_name, content FROM notes ORDER BY timestamp ASC")
            for ts_str, name, content in cursor:
                dt = datetime.fromisoformat(ts_str)
                time_str = dt.strftime("%H:%M:%S")
                prompt.append(f"{time_str} {name}: {content}")
            conn.close()
        except Exception as e:
            prompt.append(f"Error reading notes: {e}")
    prompt.append("")

    # --- Transcript ---
    prompt.append("[TRANSCRIPT]")
    if transcripts_db_path.exists():
        try:
            conn = sqlite3.connect(transcripts_db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT timestamp, username, text FROM transcripts ORDER BY timestamp ASC")
            for ts_str, name, text in cursor:
                dt = datetime.fromisoformat(ts_str)
                time_str = dt.strftime("%H:%M:%S")
                prompt.append(f"{time_str} {name}: {text}")
            conn.close()
        except Exception as e:
            prompt.append(f"Error reading transcript: {e}")
    
    # Save to file
    final_output = "\n".join(prompt)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(final_output)
    
    return final_output

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        generate_prompt(sys.argv[1])
