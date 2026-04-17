from pathlib import Path

from PIL import Image

def user_avatars_route(session_dir: Path, user_id: str) -> Path:
    return session_dir / user_id / "avatars"

def is_image(path: Path) -> bool:
    try:
        with Image.open(path) as img:
            img.verify()
            return True
    except (IOError, SyntaxError):
        return False
