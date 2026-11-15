from pathlib import Path
import os
from dotenv import load_dotenv
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
DATA_DIR = Path(os.getenv("CLIPRUSH_DATA_DIR", BASE_DIR / "data")).resolve()
UPLOAD_DIR = DATA_DIR / "uploads"
OUTPUT_DIR = DATA_DIR / "clips"
MAX_UPLOAD_MB = int(os.getenv("CLIPRUSH_MAX_UPLOAD_MB", "1024"))
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
for folder in (UPLOAD_DIR, OUTPUT_DIR): folder.mkdir(parents=True, exist_ok=True)
