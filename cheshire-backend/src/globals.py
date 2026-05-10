from dotenv import load_dotenv
from pathlib import Path
import os

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent.parent
GLOBAL_ASSETS_DIR = ROOT_DIR / "assets"

# Standardized data path for Docker volume persistence
# Default to ~/.cheshire in the user's home directory
DATA_PATH = Path(os.getenv("CHESHIRE_DATA_PATH", Path.home() / ".cheshire")).expanduser().resolve()
SESSIONS_PATH = DATA_PATH / "sessions"

# Ensure directories exist
DATA_PATH.mkdir(parents=True, exist_ok=True)
SESSIONS_PATH.mkdir(parents=True, exist_ok=True)
