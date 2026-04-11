import pytest
from fastapi import HTTPException, status

from auth.models import User, UserEntity
from auth.user_repository import InMemoryUserRepository, SqliteUserRepository
from auth.hashers import PasswordHasher

class MockPasswordHasher(PasswordHasher):
    def hash(self, password: str) -> str:
        return f"mock_hash_{password}"

    def verify(self, password: str, hashed_password: str) -> bool:
        return f"mock_hash_{password}" == hashed_password

@pytest.fixture
def hasher():
    return MockPasswordHasher()

@pytest.fixture
def repo(hasher):
    return InMemoryUserRepository(hasher=hasher)

def test_register_success(repo):
    user_entity = repo.register("alice@example.com", "password123", username="alice", full_name="Alice Liddell")
    
    assert user_entity.user.username == "alice"
    assert user_entity.user.full_name == "Alice Liddell"
    assert user_entity.user.sessions_folder is not None
    
    expected_hash_input = f"{user_entity.prefix_salt}password123{user_entity.suffix_salt}"
    assert user_entity.password_hash == f"mock_hash_{expected_hash_input}"
    
    # Check that it's actually in the repo
    assert "alice@example.com" in repo.users

def test_register_duplicate_username(repo):
    repo.register(email="bob@example.com", username="bob", password="password123")
    
    with pytest.raises(HTTPException) as excinfo:
        repo.register(email="bob@example.com", username="bob", password="different_password")
        
    assert excinfo.value.status_code == status.HTTP_409_CONFLICT
    assert excinfo.value.detail == "bob@example.com already exists"

def test_login_success(repo):
    user_entity = repo.register(email="charlie@example.com", username="charlie", password="securepassword", full_name="Charlie")
    
    logged_in_user = repo.login(email="charlie@example.com", password="securepassword")
    assert logged_in_user.user.username == "charlie"
    assert logged_in_user == user_entity

def test_login_user_not_found(repo):
    with pytest.raises(HTTPException) as excinfo:
        repo.login(email="nonexistent@example.com", password="password")
        
    assert excinfo.value.status_code == status.HTTP_404_NOT_FOUND
    assert excinfo.value.detail == "User nonexistent@example.com not found"

def test_login_invalid_password(repo):
    repo.register(email="david@example.com", username="david", password="correct_password")
    
    with pytest.raises(HTTPException) as excinfo:
        repo.login(email="david@example.com", password="wrong_password")
        
    assert excinfo.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert excinfo.value.detail == "Invalid username or password for david@example.com"

def test_login_disabled_user(repo):
    user_entity = repo.register(email="eve@example.com", username="eve", password="password_eve")
    # Manually disable user for testing
    repo.users["eve@example.com"].disabled = True
    
    with pytest.raises(HTTPException) as excinfo:
        repo.login(email="eve@example.com", password="password_eve")
        
    assert excinfo.value.status_code == status.HTTP_403_FORBIDDEN
    assert excinfo.value.detail == "eve@example.com is disabled"

@pytest.fixture
def sqlite_repo(hasher):
    # Testing with :memory:
    repo = SqliteUserRepository("file::memory:?cache=shared", hasher=hasher)
    repo.create_table_if_not_exists()
    return repo

def test_sqlite_register_success(sqlite_repo):
    user_entity = sqlite_repo.register(email="alice@example.com", username="alice", password="password123", full_name="Alice Liddell")
    assert user_entity.user.username == "alice"
    assert user_entity.user.full_name == "Alice Liddell"

def test_sqlite_register_duplicate_username(sqlite_repo):
    sqlite_repo.register(email="bob@example.com", username="bob", password="password123")
    with pytest.raises(HTTPException) as excinfo:
        sqlite_repo.register(email="bob@example.com", username="bob", password="different_password")
    assert excinfo.value.status_code == status.HTTP_409_CONFLICT
    assert excinfo.value.detail == "User with email `bob@example.com` already exists"

def test_sqlite_login_success(sqlite_repo):
    user_entity = sqlite_repo.register(email="charlie@example.com", username="charlie", password="securepassword", full_name="Charlie")
    logged_in_user = sqlite_repo.login(email="charlie@example.com", password="securepassword")
    assert logged_in_user.user.username == "charlie"
    assert logged_in_user.user.user_id == user_entity.user.user_id

def test_sqlite_login_user_not_found(sqlite_repo):
    with pytest.raises(HTTPException) as excinfo:
        sqlite_repo.login(email="nonexistent@example.com", password="password")
    assert excinfo.value.status_code == status.HTTP_404_NOT_FOUND

def test_sqlite_login_invalid_password(sqlite_repo):
    sqlite_repo.register(email="david@example.com", username="david", password="correct_password")
    with pytest.raises(HTTPException) as excinfo:
        sqlite_repo.login(email="david@example.com", password="wrong_password")
    assert excinfo.value.status_code == status.HTTP_401_UNAUTHORIZED
