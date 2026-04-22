from pathlib import Path

from PIL import Image

def is_image(path: Path) -> bool:
    try:
        with Image.open(path) as img:
            img.verify()
            return True
    except (IOError, SyntaxError):
        return False
