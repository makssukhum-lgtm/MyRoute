from dotenv import load_dotenv
import os
from pathlib import Path

BASE_DIR = Path("/home/dev/MyRoute")
load_dotenv(dotenv_path=BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Ошибка: Токен бота не найден в .env")
