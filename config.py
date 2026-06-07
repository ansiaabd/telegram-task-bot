import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
ADMIN_ID: int = int(os.getenv("ADMIN_ID", "0"))
DB_PATH: str = os.getenv("DB_PATH", "tasks.db")
CALENDAR_TYPE: str = os.getenv("CALENDAR_TYPE", "")  # "google" or "outlook"
