import os
from pathlib import Path
from typing import Annotated, Optional

from dotenv import load_dotenv

load_dotenv()

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from auth.models import User, UserEntity
from auth.dependencies import get_user_repository, create_access_token
from auth.user_repository import SqliteUserRepository

auth_router = APIRouter()

class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    full_name: Optional[str] = None


class UserResponse(BaseModel):
    """Public-facing user data returned by auth endpoints."""
    user_id: str
    username: str
    sessions_folder: str
    full_name: Optional[str] = None
    avatar_uri: Optional[str] = None
    disabled: bool = False
    created_at: str
    access_token: Optional[str] = None
    token_type: Optional[str] = None


def _to_response(entity: UserEntity, *, token: Optional[str] = None) -> UserResponse:
    return UserResponse(
        user_id=entity.user.user_id,
        username=entity.user.username,
        sessions_folder=entity.user.sessions_folder,
        full_name=entity.user.full_name,
        avatar_uri=entity.user.avatar_uri,
        disabled=entity.disabled,
        created_at=entity.created_at,
        access_token=token,
        token_type="bearer" if token else None,
    )


@auth_router.post("/login")
async def login(
    body: LoginRequest,
    repo: Annotated[SqliteUserRepository, Depends(get_user_repository)],
) -> UserResponse:
    """Authenticate an existing user with username and password."""
    entity = repo.login(body.username, body.password)
    token = create_access_token(entity.user)
    return _to_response(entity, token=token)


@auth_router.post("/register")
async def register(
    body: RegisterRequest,
    repo: Annotated[SqliteUserRepository, Depends(get_user_repository)],
) -> UserResponse:
    """Register a new user account."""
    entity = repo.register(body.username, body.password, body.full_name)
    token = create_access_token(entity.user)
    return _to_response(entity, token=token)