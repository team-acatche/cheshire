import os
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from fastapi import (
    APIRouter,
    Depends,
    FileResponse,
    HTTPException,
    status,
    UploadFile,
    File as RequestFile,
)
from pydantic import BaseModel

from endpoints.helpers.user_helpers import user_avatars_route, is_image
from auth.models import User
from auth.dependencies import get_current_user

load_dotenv()

SESSION_DIR = os.path.expanduser(os.path.expandvars(os.getenv("SESSIONS_PATH", "")))

user_router = APIRouter()

@user_router.get("/avatars/{avatar_filename}")
def get_avatar(
    avatar_filename: Annotated[str, "the filename of the avatar as stored in the server"],
    user: Annotated[User, Depends(get_current_user)],
) -> FileResponse:
    if SESSION_DIR is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="SESSION_DIR not set")
    
    session_dir = Path(SESSION_DIR)

    if avatar_filename == "default.png":
        return FileResponse(path=session_dir / "assets" / "default.png", filename="default.png")
    
    user_avatar = user_avatars_route(session_dir, user.user_id) / avatar_filename
    if is_image(user_avatar):
        return FileResponse(path=user_avatar, filename=avatar_filename)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User avatar at avatars/{avatar_filename} not found")

class UploadAvatarResponse(BaseModel):
    avatar_url: str

@user_router.post("/avatars")
def upload_avatar(
    avatar: Annotated[UploadFile, RequestFile()],
    user: Annotated[User, Depends(get_current_user)],
) -> UploadAvatarResponse:
    if SESSION_DIR is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="SESSION_DIR not set")
    session_dir = Path(SESSION_DIR)

    user_avatars_dir = user_avatars_route(session_dir, user.user_id)
    # TODO: save file on user_avatars_dir
    # TODO: update user information from database
    
    # TODO: send response 
    pass