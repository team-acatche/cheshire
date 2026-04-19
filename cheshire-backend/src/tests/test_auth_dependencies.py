"""Tests for auth.dependencies – create_access_token, get_current_user, get_user_repository."""

import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import jwt
import pytest
from fastapi import HTTPException, status

from auth.dependencies import (
    create_access_token,
    get_token,
    get_current_user,
    get_user_repository,
    JWT_ALGORITHM,
)
from auth.models import User
from auth.hashers import Argon2PasswordHasher
from auth.user_repository import SqliteUserRepository

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TEST_SECRET = "super-secret-test-key-long-enough"

TEST_USER = User(
    user_id="uid-123",
    email="alice@example.com",
    sessions_folder="uid-123",
    username="alice",
    full_name="Alice Wonderland",
    avatar_uri="avatars/alice.png",
)


def _mint_token(
    user: User = TEST_USER,
    *,
    secret: str = TEST_SECRET,
    expires_delta: timedelta | None = None,
    omit_username: bool = False,
) -> str:
    """Helper to create a JWT outside the production code for test control."""
    payload: dict = {
        "sub": user.user_id,
        "exp": datetime.now(timezone.utc) + (expires_delta or timedelta(hours=1)),
    }
    if not omit_username:
        payload["username"] = user.username
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def _setup_user_db(db_path: Path, *, disabled: bool = False) -> None:
    """Create the user table and insert TEST_USER into a real SQLite file."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path)) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user (
                user_id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                sessions_folder TEXT NOT NULL,
                username TEXT UNIQUE,
                full_name TEXT DEFAULT 'user',
                avatar_uri TEXT DEFAULT 'avatars/default.png',
                password_hash TEXT NOT NULL,
                prefix_salt TEXT NOT NULL,
                suffix_salt TEXT NOT NULL,
                disabled BOOLEAN DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute(
            "INSERT INTO user (user_id, email, sessions_folder, username, full_name, avatar_uri, "
            "password_hash, prefix_salt, suffix_salt, disabled) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                TEST_USER.user_id,
                TEST_USER.email,
                TEST_USER.sessions_folder,
                TEST_USER.username,
                TEST_USER.full_name,
                TEST_USER.avatar_uri,
                "fake-hash",
                "prefix",
                "suffix",
                int(disabled),
            ),
        )
        conn.commit()


def _create_empty_user_table(db_path: Path) -> None:
    """Create the user table without inserting any rows."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user (
                user_id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                sessions_folder TEXT NOT NULL,
                username TEXT UNIQUE,
                full_name TEXT DEFAULT 'user',
                avatar_uri TEXT DEFAULT 'avatars/default.png',
                password_hash TEXT NOT NULL,
                prefix_salt TEXT NOT NULL,
                suffix_salt TEXT NOT NULL,
                disabled BOOLEAN DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()


# ---------------------------------------------------------------------------
# create_access_token
# ---------------------------------------------------------------------------

class TestCreateAccessToken:
    """Tests for the create_access_token helper."""

    @patch("auth.dependencies.JWT_SECRET", TEST_SECRET)
    def test_returns_decodable_jwt(self):
        """Token can be decoded back and contains expected claims."""
        token = create_access_token(TEST_USER)
        payload = jwt.decode(token, TEST_SECRET, algorithms=[JWT_ALGORITHM])

        assert payload["sub"] == TEST_USER.user_id
        assert "exp" in payload

    @patch("auth.dependencies.JWT_SECRET", TEST_SECRET)
    def test_token_expiry_is_in_the_future(self):
        """The exp claim should be after the current time."""
        token = create_access_token(TEST_USER)
        payload = jwt.decode(token, TEST_SECRET, algorithms=[JWT_ALGORITHM])

        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        assert exp > datetime.now(timezone.utc)

    @patch("auth.dependencies.JWT_SECRET", "")
    def test_raises_500_when_secret_is_empty(self):
        """Missing JWT_SECRET → HTTP 500."""
        with pytest.raises(HTTPException) as exc_info:
            create_access_token(TEST_USER)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "JWT_SECRET" in exc_info.value.detail

    @patch("auth.dependencies.JWT_SECRET", TEST_SECRET)
    def test_different_users_produce_different_tokens(self):
        """Two distinct users get different tokens."""
        other = User(user_id="uid-999", email="bob@example.com", username="bob")
        token_alice = create_access_token(TEST_USER)
        token_bob = create_access_token(other)
        assert token_alice != token_bob


# ---------------------------------------------------------------------------
# get_token
# ---------------------------------------------------------------------------

class TestGetToken:
    """Tests for the get_token dependency which extracts JWT from header or cookie."""

    def test_prefers_bearer_token(self):
        """If both are present, bearer token should be preferred (or at least one of them)."""
        # Testing the logic of bearer_token or cookie_token
        token = asyncio.run(get_token(bearer_token="bearer-val", cookie_token="cookie-val"))
        assert token == "bearer-val"

    def test_falls_back_to_cookie_token(self):
        """If bearer token is missing, use cookie token."""
        token = asyncio.run(get_token(bearer_token=None, cookie_token="cookie-val"))
        assert token == "cookie-val"

    def test_raises_401_if_both_missing(self):
        """Neither header nor cookie present → HTTP 401."""
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(get_token(bearer_token=None, cookie_token=None))
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


# ---------------------------------------------------------------------------
# get_current_user
# ---------------------------------------------------------------------------

class TestGetCurrentUser:
    """Tests for the get_current_user dependency."""

    @patch("auth.dependencies.JWT_SECRET", TEST_SECRET)
    def test_returns_user_for_valid_token(self, tmp_path: Path):
        """Valid token + existing user → returns the User object."""
        db_path = tmp_path / "users.db"
        _setup_user_db(db_path)
        token = _mint_token()

        with patch("auth.dependencies.SESSIONS_PATH", tmp_path):
<<<<<<< HEAD
            user = asyncio.run(get_current_user(token=token, repo=get_user_repository()))
=======
            mock_repo = MagicMock()
            mock_repo.get_by_user_id.return_value = MagicMock(disabled=False, user=TEST_USER)
            user = asyncio.run(get_current_user(token=token, repo=mock_repo))
>>>>>>> main

        assert user.user_id == TEST_USER.user_id
        assert user.username == TEST_USER.username
        assert user.email == TEST_USER.email
        assert user.full_name == TEST_USER.full_name

    @patch("auth.dependencies.JWT_SECRET", TEST_SECRET)
    def test_expired_token_raises_401(self, tmp_path: Path):
        """Expired JWT → HTTP 401 with 'Token has expired' detail."""
        db_path = tmp_path / "users.db"
        _setup_user_db(db_path)
        token = _mint_token(expires_delta=timedelta(hours=-1))

        with patch("auth.dependencies.SESSIONS_PATH", tmp_path):
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(get_current_user(token=token, repo=get_user_repository()))

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "expired" in exc_info.value.detail.lower()

    @patch("auth.dependencies.JWT_SECRET", TEST_SECRET)
    def test_invalid_token_raises_401(self, tmp_path: Path):
        """Garbage token string → HTTP 401."""
        with patch("auth.dependencies.SESSIONS_PATH", tmp_path):
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(get_current_user(token="not.a.real.token", repo=get_user_repository()))

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    @patch("auth.dependencies.JWT_SECRET", TEST_SECRET)
    def test_wrong_secret_raises_401(self, tmp_path: Path):
        """Token signed with a different secret → HTTP 401."""
        token = _mint_token(secret="wrong-secret-but-long-enough-32b!")

        with patch("auth.dependencies.SESSIONS_PATH", tmp_path):
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(get_current_user(token=token, repo=get_user_repository()))

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    @patch("auth.dependencies.JWT_SECRET", TEST_SECRET)
    def test_user_not_in_db_raises_401(self, tmp_path: Path):
        """Valid token but username not in database → HTTP 401."""
        db_path = tmp_path / "users.db"
        _create_empty_user_table(db_path)
        token = _mint_token()

        with patch("auth.dependencies.SESSIONS_PATH", tmp_path):
            mock_repo = MagicMock()
            mock_repo.get_by_user_id.return_value = None
            with pytest.raises(HTTPException) as exc_info:
<<<<<<< HEAD
                asyncio.run(get_current_user(token=token, repo=get_user_repository()))
=======
                asyncio.run(get_current_user(token=token, repo=mock_repo))
>>>>>>> main

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    @patch("auth.dependencies.JWT_SECRET", TEST_SECRET)
    def test_disabled_user_raises_403(self, tmp_path: Path):
        """Valid token for a disabled user → HTTP 403."""
        db_path = tmp_path / "users.db"
        _setup_user_db(db_path, disabled=True)
        token = _mint_token()

        with patch("auth.dependencies.SESSIONS_PATH", tmp_path):
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(get_current_user(token=token, repo=get_user_repository()))

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "disabled" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# get_user_repository
# ---------------------------------------------------------------------------

class TestGetUserRepository:
    """Tests for the get_user_repository dependency."""

    def test_returns_sqlite_repo(self, tmp_path: Path):
        """Should return a SqliteUserRepository instance."""
        with patch("auth.dependencies.SESSIONS_PATH", tmp_path):
            repo = get_user_repository()

        assert isinstance(repo, SqliteUserRepository)

    def test_creates_users_table(self, tmp_path: Path):
        """The returned repo should have the user table ready."""
        with patch("auth.dependencies.SESSIONS_PATH", tmp_path):
            repo = get_user_repository()

        db_path = tmp_path / "users.db"
        assert db_path.exists()

        with sqlite3.connect(str(db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user'")
            assert cursor.fetchone() is not None
