import io
import pytest
from pathlib import Path
from fastapi import status
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from server import api
from auth.dependencies import get_current_user, get_user_repository
from dependencies.sessions import get_user_path
from auth.models import User, UserEntity

client = TestClient(api)

TEST_USER = User(
    user_id="test-123",
    email="test@example.com",
    sessions_folder="test-123",
    username="testuser",
    full_name="Test User",
)

@pytest.fixture
def test_setup(tmp_path):
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()
    
    assets_dir = tmp_path / "global_assets"
    assets_dir.mkdir()
    (assets_dir / "default.png").write_bytes(b"fake default.png")
    
    user_path = session_dir / TEST_USER.user_id
    user_path.mkdir()
    (user_path / "avatars").mkdir()
    
    return {
        "session_dir": session_dir,
        "assets_dir": assets_dir,
        "user_path": user_path
    }

@pytest.fixture(autouse=True)
def setup_overrides():
    # Clear overrides before and after each test
    api.dependency_overrides.clear()
    yield
    api.dependency_overrides.clear()

def test_get_avatar_default(test_setup):
    session_dir = test_setup["session_dir"]
    assets_dir = test_setup["assets_dir"]
    user_path = test_setup["user_path"]
    
    api.dependency_overrides[get_user_path] = lambda: user_path
    
    with patch("endpoints.user.SESSIONS_PATH", str(session_dir)), \
         patch("endpoints.user.GLOBAL_ASSETS_DIR", assets_dir):
        response = client.get("/api/v1/avatars/default.png")
    
        assert response.status_code == status.HTTP_200_OK
        assert response.content == b"fake default.png"

def test_get_avatar_user_exists(test_setup):
    session_dir = test_setup["session_dir"]
    user_path = test_setup["user_path"]
    avatar_file = user_path / "avatars" / "my_avatar.png"
    avatar_file.write_bytes(b"fake avatar")
    
    api.dependency_overrides[get_user_path] = lambda: user_path
    
    with patch("endpoints.user.SESSIONS_PATH", str(session_dir)):
        # Mock is_image to return True
        with patch("endpoints.user.is_image", return_value=True):
            response = client.get("/api/v1/avatars/my_avatar.png")
    
            assert response.status_code == status.HTTP_200_OK
            assert response.content == b"fake avatar"

def test_get_avatar_not_found(test_setup):
    session_dir = test_setup["session_dir"]
    user_path = test_setup["user_path"]
    
    api.dependency_overrides[get_user_path] = lambda: user_path
    
    with patch("endpoints.user.SESSIONS_PATH", str(session_dir)):
        response = client.get("/api/v1/avatars/non_existent.png")
    
        assert response.status_code == status.HTTP_404_NOT_FOUND

def test_upload_avatar(test_setup):
    session_dir = test_setup["session_dir"]
    user_path = test_setup["user_path"]
    mock_repo = MagicMock()
    
    # Mock update_avatar to return a UserEntity with updated avatar_uri
    updated_user_entity = UserEntity(
        user=User(**TEST_USER.model_dump()),
        password_hash="...",
        prefix_salt="...",
        suffix_salt="...",
        created_at="..."
    )
    updated_user_entity.user.avatar_uri = "avatars/uploaded.png"
    mock_repo.update_avatar.return_value = updated_user_entity

    api.dependency_overrides[get_current_user] = lambda: TEST_USER
    api.dependency_overrides[get_user_path] = lambda: user_path
    api.dependency_overrides[get_user_repository] = lambda: mock_repo
    
    with patch("endpoints.user.SESSIONS_PATH", str(session_dir)):
        file_content = b"uploaded image content"
        files = {"avatar": ("test.png", io.BytesIO(file_content), "image/png")}
        response = client.post("/api/v1/avatars", files=files)
    
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"avatar_url": "/api/v1/avatars/uploaded.png"}
    
        # Check if file was actually written (filename has timestamp prefix)
        avatars_dir = user_path / "avatars"
        files_in_dir = list(avatars_dir.glob("*__test.png"))
        assert len(files_in_dir) == 1
        assert files_in_dir[0].read_bytes() == file_content
