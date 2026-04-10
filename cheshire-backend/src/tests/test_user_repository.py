import pytest
from fastapi import HTTPException

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
    user_entity = repo.register(username="alice", password="password123", full_name="Alice Liddell")
    
    assert user_entity.user.username == "alice"
    assert user_entity.user.full_name == "Alice Liddell"
    assert user_entity.user.sessions_folder == "alice"
    
    expected_hash_input = f"{user_entity.prefix_salt}password123{user_entity.suffix_salt}"
    assert user_entity.password_hash == f"mock_hash_{expected_hash_input}"
    
    # Check that it's actually in the repo
    assert "alice" in repo.users

def test_register_duplicate_username(repo):
    repo.register(username="bob", password="password123")
    
    with pytest.raises(HTTPException) as excinfo:
        repo.register(username="bob", password="different_password")
        
    assert excinfo.value.status_code == 409
    assert excinfo.value.detail == "User bob already exists"

def test_login_success(repo):
    user_entity = repo.register(username="charlie", password="securepassword", full_name="Charlie")
    
    logged_in_user = repo.login(username="charlie", password="securepassword")
    assert logged_in_user.user.username == "charlie"
    assert logged_in_user == user_entity

def test_login_user_not_found(repo):
    with pytest.raises(HTTPException) as excinfo:
        repo.login(username="nonexistent", password="password")
        
    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "User nonexistent not found"

def test_login_invalid_password(repo):
    repo.register(username="david", password="correct_password")
    
    with pytest.raises(HTTPException) as excinfo:
        repo.login(username="david", password="wrong_password")
        
    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "Invalid password for user david"

def test_login_disabled_user(repo):
    user_entity = repo.register(username="eve", password="password_eve")
    # Manually disable user for testing
    repo.users["eve"].disabled = True
    
    with pytest.raises(HTTPException) as excinfo:
        repo.login(username="eve", password="password_eve")
        
    assert excinfo.value.status_code == 403
    assert excinfo.value.detail == "User eve is disabled"

@pytest.fixture
def sqlite_repo(hasher):
    # Testing with :memory:
    repo = SqliteUserRepository("file::memory:?cache=shared", hasher=hasher)
    repo.create_table_if_not_exists()
    return repo

def test_sqlite_register_success(sqlite_repo):
    user_entity = sqlite_repo.register(username="alice", password="password123", full_name="Alice Liddell")
    assert user_entity.user.username == "alice"
    assert user_entity.user.full_name == "Alice Liddell"

def test_sqlite_register_duplicate_username(sqlite_repo):
    sqlite_repo.register(username="bob", password="password123")
    with pytest.raises(HTTPException) as excinfo:
        sqlite_repo.register(username="bob", password="different_password")
    assert excinfo.value.status_code == 409
    assert excinfo.value.detail == "User bob already exists"

def test_sqlite_login_success(sqlite_repo):
    user_entity = sqlite_repo.register(username="charlie", password="securepassword", full_name="Charlie")
    logged_in_user = sqlite_repo.login(username="charlie", password="securepassword")
    assert logged_in_user.user.username == "charlie"
    assert logged_in_user.user.user_id == user_entity.user.user_id

def test_sqlite_login_user_not_found(sqlite_repo):
    with pytest.raises(HTTPException) as excinfo:
        sqlite_repo.login(username="nonexistent", password="password")
    assert excinfo.value.status_code == 404

def test_sqlite_login_invalid_password(sqlite_repo):
    sqlite_repo.register(username="david", password="correct_password")
    with pytest.raises(HTTPException) as excinfo:
        sqlite_repo.login(username="david", password="wrong_password")
    assert excinfo.value.status_code == 401
