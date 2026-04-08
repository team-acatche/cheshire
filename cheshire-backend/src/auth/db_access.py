import os
from pathlib import Path
from typing import Annotated, AsyncGenerator
import sqlite3

from fastapi import HTTPException 

from knowledge_base.history import EventRepository, SqliteEventRepository

SESSION_DIR = os.path.expanduser(os.path.expandvars(os.getenv("SESSIONS_PATH", "")))

async def get_history(
    # TODO: these are path params, and are prone to session hijacking
    username: Annotated[str, "The username of the user"],
) -> AsyncGenerator[EventRepository, None]:
    if not SESSION_DIR:
        raise HTTPException(status_code=500, detail="SESSION_DIR not set")
    
    user_path = Path(SESSION_DIR) / username

    with sqlite3.connect(user_path / f"{username}.sqlite") as history_db:
        yield SqliteEventRepository(history_db)
