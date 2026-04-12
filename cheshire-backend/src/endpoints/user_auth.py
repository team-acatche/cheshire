import os
from pathlib import Path
from typing import Annotated, Optional

from dotenv import load_dotenv

load_dotenv()

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from auth.models import User, UserEntity
from auth.dependencies import get_user_repository, create_access_token
from auth.user_repository import SqliteUserRepository

auth_router = APIRouter()

class RegisterRequest(BaseModel):
    email: str
    password: str
    username: Optional[str] = None
    full_name: Optional[str] = None


class UserResponse(BaseModel):
    """Public-facing user data returned by auth endpoints."""
    user_id: str
    email: str
    sessions_folder: str
    username: Optional[str] = None
    full_name: Optional[str] = None
    avatar_uri: str = "avatars/default.png"
    disabled: bool = False
    created_at: str
    access_token: Optional[str] = None
    token_type: Optional[str] = None


def _to_response(entity: UserEntity, *, token: Optional[str] = None) -> UserResponse:
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
        access_token=token,
        token_type="bearer" if token else None,
    )


@auth_router.post("/login")
async def login(
    repo: Annotated[SqliteUserRepository, Depends(get_user_repository)],
    body: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> UserResponse:
    """Authenticate an existing user with username and password."""
    entity = repo.login(body.username, body.password)
    token = create_access_token(entity.user)
    return _to_response(entity, token=token)


@auth_router.post("/register")
async def register(
    repo: Annotated[SqliteUserRepository, Depends(get_user_repository)],
    body: RegisterRequest,
) -> UserResponse:
    """Register a new user account."""
    entity = repo.register(body.email, body.password, username=body.username, full_name=body.full_name)
    token = create_access_token(entity.user)
    return _to_response(entity, token=token)