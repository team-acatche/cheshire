import os
from pathlib import Path
from typing import Annotated, AsyncGenerator
import sqlite3

from fastapi import HTTPException, Depends, status

from auth.models import User
from auth.dependencies import get_current_user
from knowledge_base.history import EventRepository, SqliteEventRepository

from dependencies.sessions import get_user_db_path
from knowledge_base.history import EventRepository, SqliteEventRepository

async def get_history(
    user_db_path: Annotated[Path, Depends(get_user_db_path)]
) -> AsyncGenerator[EventRepository, None]:
    with sqlite3.connect(user_db_path) as history_db:
        yield SqliteEventRepository(history_db)
