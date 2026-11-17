"""Central configuration, read from environment variables (and a local .env file)."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _int_env(name: str, default: int, minimum: int = 0) -> int:
    """Read an integer env var; fall back to the default on junk instead of crashing at import."""
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except ValueError:
        return default


DATA_DIR = Path(os.getenv("CLIPRUSH_DATA_DIR", BASE_DIR / "data")).resolve()
UPLOAD_DIR = DATA_DIR / "uploads"
OUTPUT_DIR = DATA_DIR / "clips"
STATE_FILE = DATA_DIR / "state.json"

MAX_UPLOAD_MB = _int_env("CLIPRUSH_MAX_UPLOAD_MB", 1024, minimum=1)
MAX_CONCURRENT_JOBS = _int_env("CLIPRUSH_MAX_CONCURRENT_JOBS", 1, minimum=1)
RETENTION_HOURS = _int_env("CLIPRUSH_RETENTION_HOURS", 24)  # 0 disables auto-cleanup

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}

for folder in (UPLOAD_DIR, OUTPUT_DIR):
    folder.mkdir(parents=True, exist_ok=True)
