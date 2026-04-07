import os
from pathlib import Path
from typing import Annotated, AsyncGenerator
import sqlite3

from fastapi import HTTPException 

from knowledge_base.history import SimplerEventRepository, SqliteEventRepository

SESSION_DIR = os.path.expanduser(os.path.expandvars(os.getenv("SESSIONS_PATH", "")))

async def get_history(
    # TODO: these are path params, and are prone to session hijacking
    username: Annotated[str, "The username of the user"],
    session_id: Annotated[str, "The session ID for the document."],
) -> AsyncGenerator[SimplerEventRepository, None]:
    if not SESSION_DIR:
        raise HTTPException(status_code=500, detail="SESSION_DIR not set")
    
    session_path = Path(SESSION_DIR) / username / session_id

    with sqlite3.connect(session_path / "history.sqlite") as history_db:
        yield SimplerEventRepository(session_id=session_id, repo=SqliteEventRepository(history_db))
