from pathlib import Path
from typing import Annotated
from fastapi import Depends, HTTPException, status

from auth.dependencies import SESSIONS_PATH, get_current_user # type: ignore
from auth.models import User # type: ignore

async def get_user_path(
    current_user: Annotated[User, Depends(get_current_user)],
) -> Path:
    """Dependency that returns the path to the current user's session directory."""
    if not SESSIONS_PATH:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SESSIONS_PATH not set",
        )
    
    user_path = SESSIONS_PATH / current_user.user_id
    return user_path

async def get_user_db_path(
    user_path: Annotated[Path, Depends(get_user_path)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Path:
    """Dependency that returns the path to the current user's sqlite database."""
    return user_path / f"{current_user.user_id}.sqlite"
