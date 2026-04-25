import pytest
from pathlib import Path
from PIL import Image
import io
from endpoints.helpers.user_helpers import is_image

@pytest.fixture
def temp_dir(tmp_path):
    return tmp_path

def test_is_image_valid_png(temp_dir):
    img_path = temp_dir / "valid.png"
    img = Image.new("RGB", (10, 10), color="red")
    img.save(img_path)
    
    assert is_image(img_path) is True

def test_is_image_valid_jpeg(temp_dir):
    img_path = temp_dir / "valid.jpg"
    img = Image.new("RGB", (10, 10), color="blue")
    img.save(img_path)
    
    assert is_image(img_path) is True

def test_is_image_invalid_text_file(temp_dir):
    file_path = temp_dir / "not_an_image.txt"
    file_path.write_text("This is just some text, not an image.")
    
    assert is_image(file_path) is False

def test_is_image_non_existent_file(temp_dir):
    file_path = temp_dir / "does_not_exist.png"
    
    assert is_image(file_path) is False

def test_is_image_corrupted_file(temp_dir):
    file_path = temp_dir / "corrupted.png"
    # Write some random bytes that are not a valid PNG header
    file_path.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR\x00\x00\x00") 
    # Truncated or malformed
    
    # Depending on how PIL handles it, open() might succeed but verify() fail, 
    # or open() might fail immediately.
    assert is_image(file_path) is False

def test_is_image_empty_file(temp_dir):
    file_path = temp_dir / "empty.png"
    file_path.write_bytes(b"")
    
    assert is_image(file_path) is False

def test_is_image_directory(temp_dir):
    dir_path = temp_dir / "a_directory"
    dir_path.mkdir()
    
    assert is_image(dir_path) is False
