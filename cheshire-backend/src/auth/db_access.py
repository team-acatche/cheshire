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
    
    user_id = user.user_id
    user_path = Path(SESSION_DIR) / user_id

    with sqlite3.connect(user_path / f"{user_id}.sqlite") as history_db:
        yield SqliteEventRepository(history_db)
