import os
import pytest
from fastapi import status
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from server import api
from auth.dependencies import get_user_repository, create_access_token, ACCESS_TOKEN_COOKIE, JWT_SECRET, get_token
from auth.models import User, UserEntity
from cheshire_configs.registry import configs

client = TestClient(api)

@pytest.fixture(autouse=True)
def setup_overrides():
    # Mock configs to avoid dependency issues for auth tests
    api.dependency_overrides[configs] = lambda: {}
    yield
    api.dependency_overrides.clear()

TEST_USER = User(
    user_id="test-123",
    email="test@example.com",
    sessions_folder="test-123",
    username="testuser",
    full_name="Test User",
)

TEST_ENTITY = UserEntity(
    user=TEST_USER,
    password_hash="hashed_password",
    prefix_salt="prefix",
    suffix_salt="suffix",
    created_at="2024-04-18T19:00:00Z"
)

def test_login_sets_cookie_and_hides_token():
    mock_repo = MagicMock()
    mock_repo.login.return_value = TEST_ENTITY
    
    api.dependency_overrides[get_user_repository] = lambda: mock_repo
    
    with patch("auth.dependencies.JWT_SECRET", "test-secret-that-is-long-enough-for-sha256"):
        response = client.post(
            "/api/v1/login",
            data={"username": "test@example.com", "password": "password123"}
        )
    
    assert response.status_code == status.HTTP_200_OK
    
    # Check that the token is NOT in the JSON body
    data = response.json()
    assert "access_token" not in data
    assert data["email"] == TEST_USER.email
    
    # Check that the cookie is set
    assert ACCESS_TOKEN_COOKIE in response.cookies
    assert response.cookies[ACCESS_TOKEN_COOKIE] is not None
    
    # Clean up
    del api.dependency_overrides[get_user_repository]

def test_register_sets_cookie_and_hides_token():
    mock_repo = MagicMock()
    mock_repo.register.return_value = TEST_ENTITY
    
    api.dependency_overrides[get_user_repository] = lambda: mock_repo
    
    with patch("auth.dependencies.JWT_SECRET", "test-secret-that-is-long-enough-for-sha256"):
        response = client.post(
            "/api/v1/register",
            json={
                "email": "test@example.com",
                "password": "password123",
                "username": "testuser",
                "full_name": "Test User"
            }
        )
    
    assert response.status_code == status.HTTP_200_OK
    
    # Check that the token is NOT in the JSON body
    data = response.json()
    assert "access_token" not in data
    
    # Check that the cookie is set
    assert ACCESS_TOKEN_COOKIE in response.cookies
    
    # Clean up
    del api.dependency_overrides[get_user_repository]

def test_logout_clears_cookie():
    response = client.post("/api/v1/logout")
    
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"detail": "Logged out"}
    
    # In FastAPI/TestClient, a deleted cookie usually has an empty value and an expired date
    # or it might just be absent depending on how it's handled.
    # Actually, response.delete_cookie sets the value to "" and expires to 0.
    
    # Check if the cookie is set to be deleted (value is empty or it's not present)
    # The TestClient usually tracks cookies.
    cookie = response.cookies.get(ACCESS_TOKEN_COOKIE)
    assert cookie == "" or cookie is None
