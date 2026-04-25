"""
FastAPI dependencies for user authentication.

Provides:
- get_user_repository: Yields a SqliteUserRepository backed by SESSIONS_PATH/users.db.
- get_current_user: Reads a JWT from either the Authorization header or the HttpOnly cookie.
- create_access_token: Helper to mint a signed JWT for a given User.
"""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Optional

import dotenv
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyCookie, OAuth2PasswordBearer

from globals import SESSION_DIR
from auth.hashers import Argon2PasswordHasher
from auth.models import User
from auth.user_repository import SqliteUserRepository

dotenv.load_dotenv()

SESSIONS_PATH = Path(SESSION_DIR)

JWT_SECRET: str = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM: str = "HS256"
JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "24"))

ACCESS_TOKEN_COOKIE = "access_token"

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/login",
    auto_error=False,
)

cookie_scheme = APIKeyCookie(
    name=ACCESS_TOKEN_COOKIE,
    auto_error=False,
)


def get_user_repository() -> SqliteUserRepository:
    db_path = SESSIONS_PATH / "users.db"
    hasher = Argon2PasswordHasher()
    repo = SqliteUserRepository(db_path=db_path, hasher=hasher)
    repo.create_table_if_not_exists()
    return repo


def create_access_token(user: User) -> str:
    if not JWT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWT_SECRET is not configured on the server.",
        )
    payload = {
        "sub": user.user_id,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def get_token(
    bearer_token: Annotated[Optional[str], Depends(oauth2_scheme)],
    cookie_token: Annotated[Optional[str], Depends(cookie_scheme)],
) -> str:
    token = bearer_token or cookie_token
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


async def get_current_user(
    token: Annotated[str, Depends(get_token)],
    repo: Annotated[SqliteUserRepository, Depends(get_user_repository)],
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired, please log in again",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise credentials_exception

    entity = repo.get_by_user_id(user_id)
    if entity is None:
        raise credentials_exception

    if entity.disabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    return entity.user
