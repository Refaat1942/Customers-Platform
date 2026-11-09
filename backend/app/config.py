import os
import secrets
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parents[2] / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

DB_PATH = Path(os.environ.get("DB_PATH", DATA_DIR / "platform.duckdb"))

FRONTEND_DIST = Path(
    os.environ.get("FRONTEND_DIST", Path(__file__).resolve().parents[2] / "frontend" / "dist")
)


def _secret_key() -> str:
    key = os.environ.get("SECRET_KEY")
    if key:
        return key
    f = DATA_DIR / ".secret_key"
    if not f.exists():
        f.write_text(secrets.token_urlsafe(48))
        f.chmod(0o600)
    return f.read_text().strip()


SECRET_KEY = _secret_key()
TOKEN_HOURS = int(os.environ.get("TOKEN_HOURS", "12"))

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")  # used only when no users exist yet

MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "200"))

DEFAULT_SETTINGS = {
    "active_days": 30,         # last visit within N days -> Active
    "attention_days": 60,      # within N days -> Needs Attention, older -> Inactive
    "high_value_spend": 10000,  # total spend >= N -> High Value
    "loyalty_spend": 10000,     # loyal if spend >= N ...
    "loyalty_visits": 5,        # ... or visits >= N
}
