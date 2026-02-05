from datetime import datetime, timezone
from zoneinfo import ZoneInfo

timestamp = datetime.now(ZoneInfo("Asia/Colombo")).isoformat(timespec="milliseconds")
print(timestamp)
