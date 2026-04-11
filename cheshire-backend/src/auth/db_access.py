import os
from pathlib import Path
from typing import Annotated, AsyncGenerator
import sqlite3

from fastapi import HTTPException, Depends, status

from auth.models import User
from auth.dependencies import get_current_user
from knowledge_base.history import EventRepository, SqliteEventRepository

SESSION_DIR = os.path.expanduser(os.path.expandvars(os.getenv("SESSIONS_PATH", "")))

async def get_history(
    user: Annotated[User, Depends(get_current_user)]
) -> AsyncGenerator[EventRepository, None]:
    if not SESSION_DIR:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="SESSION_DIR not set")
    
    username = user.username
    user_path = Path(SESSION_DIR) / username

    with sqlite3.connect(user_path / f"{username}.sqlite") as history_db:
        yield SqliteEventRepository(history_db)
