"""Setări citite din fișierul .env (nu mai ținem token-ul în cod)."""
import os

from dotenv import load_dotenv

load_dotenv()


def _int(name, default):
    return int(os.getenv(name, default))


TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
# Doar aceste chat-uri pot folosi botul (separate prin virgulă). Gol = oricine.
ALLOWED_CHAT_IDS = {int(x) for x in os.getenv("ALLOWED_CHAT_IDS", "").split(",") if x.strip()}

CHECK_INTERVAL_MIN = _int("CHECK_INTERVAL_MIN", 15)
MAX_CONCURRENCY = _int("MAX_CONCURRENCY", 16)       # cereri simultane în total
PER_DOMAIN_CONCURRENCY = _int("PER_DOMAIN_CONCURRENCY", 2)  # politicos cu fiecare site
REQUEST_TIMEOUT = _int("REQUEST_TIMEOUT", 20)
MAX_RETRIES = _int("MAX_RETRIES", 3)

# Alerte
MIN_CHANGE_PCT = float(os.getenv("MIN_CHANGE_PCT", "0"))  # ignoră variații mai mici de X%
NOTIFY_ON_RISE = os.getenv("NOTIFY_ON_RISE", "1") == "1"
FAILS_BEFORE_WARNING = _int("FAILS_BEFORE_WARNING", 3)

# Fallback cu browser real (Playwright) pentru site-uri care randează prețul din JS.
USE_BROWSER_FALLBACK = os.getenv("USE_BROWSER_FALLBACK", "0") == "1"

DB_PATH = os.getenv("DB_PATH", "pricebot.db")
LOG_FILE = os.getenv("LOG_FILE", "pricebot.log")
