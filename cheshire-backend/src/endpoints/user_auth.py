import os
from pathlib import Path
from typing import Annotated, Optional

from dotenv import load_dotenv

load_dotenv()

<<<<<<< HEAD
from fastapi import APIRouter, Depends, Response
=======
from fastapi import APIRouter, Depends
>>>>>>> main
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from auth.models import User, UserEntity
from auth.dependencies import get_user_repository, create_access_token, JWT_EXPIRY_HOURS
from auth.user_repository import SqliteUserRepository

auth_router = APIRouter()

# Cookie name the server sets and the client echoes back automatically.
ACCESS_TOKEN_COOKIE = "access_token"


class RegisterRequest(BaseModel):
    email: str
    password: str
    username: Optional[str] = None
    full_name: Optional[str] = None


class UserResponse(BaseModel):
    """Public-facing user data returned by auth endpoints (no token field)."""
    user_id: str
    email: str
    sessions_folder: str
    username: Optional[str] = None
    full_name: Optional[str] = None
    avatar_uri: str = "avatars/default.png"
    disabled: bool = False
    created_at: str


def _to_response(entity: UserEntity) -> UserResponse:
    assert entity.user.sessions_folder is not None, "Sessions folder should not be None"
    return UserResponse(
        user_id=entity.user.user_id,
        email=entity.user.email,
        sessions_folder=entity.user.sessions_folder,
        username=entity.user.username,
        full_name=entity.user.full_name,
        avatar_uri=entity.user.avatar_uri,
        disabled=entity.disabled,
        created_at=entity.created_at,
    )


def _set_auth_cookie(response: Response, token: str) -> None:
    """Attach the JWT as an HttpOnly, SameSite=Strict cookie."""
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE,
        value=token,
        httponly=True,                        # JS cannot read this cookie
        samesite="strict",                    # never sent on cross-site requests
        secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",  # True in production (HTTPS)
        max_age=JWT_EXPIRY_HOURS * 3600,      # mirrors the JWT expiry
        path="/",
    )


@auth_router.post("/login")
async def login(
    response: Response,
    repo: Annotated[SqliteUserRepository, Depends(get_user_repository)],
    body: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> UserResponse:
    """Authenticate an existing user.

    On success the JWT is returned as an HttpOnly; SameSite=Strict cookie.
    The response body carries only public profile fields — the token is
    intentionally absent from JSON so it cannot be accessed by JS.
    """
    entity = repo.login(body.username, body.password)
    token = create_access_token(entity.user)
    _set_auth_cookie(response, token)
    return _to_response(entity)


@auth_router.post("/logout")
async def logout(response: Response) -> dict:
    """Clear the auth cookie by overwriting it with an immediately-expired one."""
    response.delete_cookie(
        key=ACCESS_TOKEN_COOKIE,
        httponly=True,
        samesite="strict",
        secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        path="/",
    )
    return {"detail": "Logged out"}


@auth_router.post("/register")
async def register(
    response: Response,
    repo: Annotated[SqliteUserRepository, Depends(get_user_repository)],
    body: RegisterRequest,
) -> UserResponse:
    """Register a new user account and log them in immediately."""
    entity = repo.register(body.email, body.password, username=body.username, full_name=body.full_name)
    token = create_access_token(entity.user)
    _set_auth_cookie(response, token)
    return _to_response(entity)
