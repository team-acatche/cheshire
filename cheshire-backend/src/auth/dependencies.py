"""
FastAPI dependencies for user authentication.

Provides:
- get_user_repository: Yields a SqliteUserRepository backed by SESSIONS_PATH/users.db.
- get_current_user: Decodes a JWT bearer token and returns the authenticated User.
- create_access_token: Helper to mint a signed JWT for a given User.
"""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import dotenv

from auth.hashers import Argon2PasswordHasher
from auth.models import User
from auth.user_repository import SqliteUserRepository

dotenv.load_dotenv()

SESSIONS_PATH = Path(
    os.path.expandvars(
        os.path.expanduser(os.getenv("SESSIONS_PATH", "~/.cache/cheshire"))
    )
)

JWT_SECRET: str = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM: str = "HS256"
JWT_EXPIRY_HOURS: int = int(os.getenv("JWT_EXPIRY_HOURS", "24"))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/login")

def get_user_repository() -> SqliteUserRepository:
    """Return a ready-to-use SqliteUserRepository."""
    db_path = SESSIONS_PATH / "users.db"
    hasher = Argon2PasswordHasher()
    repo = SqliteUserRepository(db_path=db_path, hasher=hasher)
    repo.create_table_if_not_exists()
    return repo


def create_access_token(user: User) -> str:
    """Mint a signed JWT containing the user's identity."""
    if not JWT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWT_SECRET is not configured on the server.",
        )
    payload = {
        "sub": user.user_id,
        "username": user.username,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    repo: Annotated[SqliteUserRepository, Depends(get_user_repository)],
) -> User:
    """Decode a bearer token and return the corresponding User.

    Raises 401 if the token is invalid, expired, or references a
    non-existent / disabled user.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username: str | None = payload.get("username")
        if username is None:
            raise credentials_exception
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise credentials_exception

    # find the user in the database
    from auth.user_repository import SqliteUserRepository as _Repo
    import sqlite3

    db_path = SESSIONS_PATH / "users.db"
    with sqlite3.connect(db_path, uri=True) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT user_id, username, sessions_folder, full_name, avatar_uri, disabled "
            "FROM user WHERE username = ? LIMIT 1;",
            (username,),
        )
        row = cursor.fetchone()

    if row is None:
        raise credentials_exception

    user_id, username, sessions_folder, full_name, avatar_uri, disabled = row
    if disabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User named {username} not found",
        )

    return User(
        user_id=user_id,
        username=username,
        sessions_folder=sessions_folder,
        full_name=full_name,
        avatar_uri=avatar_uri,
    )
