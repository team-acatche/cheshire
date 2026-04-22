from dotenv import load_dotenv
from pathlib import Path
import os

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent
GLOBAL_ASSETS_DIR = ROOT_DIR / "assets"

SESSION_DIR = os.path.expanduser(os.path.expandvars(os.getenv("SESSIONS_PATH", "")))
