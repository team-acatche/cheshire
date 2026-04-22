from datetime import datetime
import os
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    UploadFile,
    File as RequestFile,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel

from endpoints.helpers.user_helpers import is_image
from auth.models import User
from dependencies.sessions import get_user_path
from auth.dependencies import get_user_repository, get_current_user
from auth.user_repository import UserRepository

from globals import GLOBAL_ASSETS_DIR, SESSION_DIR

user_router = APIRouter()

@user_router.get("/avatars/{avatar_filename}")
def get_avatar(
    avatar_filename: Annotated[str, "the filename of the avatar as stored in the server"],
    user_path: Annotated[Path, Depends(get_user_path)],
) -> FileResponse:
    if SESSION_DIR is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="SESSION_DIR not set")
    
    session_dir = Path(SESSION_DIR)

    # TODO: bugfix -- add the default avatar
    if avatar_filename == "default.png":
        return FileResponse(path=GLOBAL_ASSETS_DIR / "default.png", filename="default.png")
    
    user_avatar = user_path / "avatars" / avatar_filename
    if is_image(user_avatar):
        return FileResponse(path=user_avatar, filename=avatar_filename)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User avatar at avatars/{avatar_filename} not found")

class UploadAvatarResponse(BaseModel):
    avatar_url: str

@user_router.post("/avatars")
async def upload_avatar(
    avatar: Annotated[UploadFile, RequestFile()],
    user: Annotated[User, Depends(get_current_user)],
    user_path: Annotated[Path, Depends(get_user_path)],
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
) -> UploadAvatarResponse:
    if SESSION_DIR is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="SESSION_DIR not set")
    session_dir = Path(SESSION_DIR)

    # write avatar to disk
    user_avatars_dir = user_path / "avatars"
    avatar_filename = f"{datetime.now()}__{avatar.filename}"
    with open(user_avatars_dir / avatar_filename, "wb") as f:
        f.write(await avatar.read())
    updated_user = user_repository.update_avatar(user.user_id, f"avatars/{avatar_filename}")
    
    return UploadAvatarResponse(avatar_url=f"/api/v1/{updated_user.user.avatar_uri}")