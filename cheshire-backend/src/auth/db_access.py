from pathlib import Path
from typing import Annotated, AsyncGenerator
import sqlite3

from fastapi import Depends

from knowledge_base.history import EventRepository, SqliteEventRepository

from dependencies.sessions import get_user_db_path

async def get_history(
    user_db_path: Annotated[Path, Depends(get_user_db_path)]
) -> AsyncGenerator[EventRepository, None]:
    with sqlite3.connect(user_db_path) as history_db:
        yield SqliteEventRepository(history_db)
