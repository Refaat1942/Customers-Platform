import os
import secrets
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parents[2] / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://customers:customers@localhost:5432/customers")

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
# first start only (when there are no users): admin / admin  -> change it after logging in
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")

MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "1024"))
BRANDING_DIR = DATA_DIR / "branding"
BRANDING_DIR.mkdir(exist_ok=True)

DEFAULT_SETTINGS = {
    "active_days": 30,         # last visit within N days -> Active
    "attention_days": 60,      # within N days -> Needs Attention, older -> Inactive
    "high_value_spend": 10000,  # total spend >= N -> High Value
    "loyalty_spend": 10000,     # loyal if spend >= N ...
    "loyalty_visits": 5,        # ... or visits >= N
    "app_name": "Customers Platform",
    "primary_color": "#1b5e20",
    "openai_api_key": os.environ.get("OPENAI_API_KEY", ""),
    "openai_model": os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"),
}
