import os
import sqlite3
from dotenv import load_dotenv

load_dotenv()
from pathlib import Path
from typing import Annotated, Optional, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from haystack.components.agents import Agent
from haystack.tools import Tool
from haystack.dataclasses import ChatMessage
from haystack_integrations.components.embedders.fastembed import FastembedTextEmbedder

from cheshire_configs.core import PipelineConfig
from cheshire_configs.resolver import resolve_config
from knowledge_base.history import Event, EventType, SqliteEventRepository, StreamCallbackFactory
from knowledge_base.session_manager import SqliteSessionRepository, Session
from endpoints.helpers import get_or_create_vector_stores
from tools.knowledge import get_relevant_facts_tool
from auth.models import User
from auth.dependencies import get_current_user

chat_router = APIRouter()
SESSION_DIR = os.path.expanduser(os.path.expandvars(os.getenv("SESSIONS_PATH", ""))) if os.getenv("SESSIONS_PATH") else None

class ChatBody(BaseModel):
    message: str

@chat_router.get("/")
async def get_sessions(
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[Session]:
    if SESSION_DIR is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="SESSION_DIR not set")

    user_id = current_user.user_id
    session_db_path = Path(SESSION_DIR) / user_id / f"{user_id}.sqlite"
    if not session_db_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    with sqlite3.connect(session_db_path) as session_db:
        session_repo = SqliteSessionRepository(session_db)
        return session_repo.get_sessions()
    
@chat_router.get("/{session_id}")
async def chat_history(
    session_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
):
    if SESSION_DIR is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="SESSION_DIR not set")

    user_id = current_user.user_id
    history_db_path = Path(SESSION_DIR) / user_id / f"{user_id}.sqlite"
    
    if not history_db_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    # Connect to repositories
    with sqlite3.connect(history_db_path) as history_db:
        history_repo = SqliteEventRepository(history_db)
        
        recent_events = history_repo.get_recent(session_id, 1000)
        # Events are returned in DESC order, we need them in ASC order for context
        messages = [e.to_chat_message() for e in reversed(recent_events)]
        return {"messages": messages}

@chat_router.post("/{session_id}")
async def chat(
    session_id: str,
    body: ChatBody,
    current_user: Annotated[User, Depends(get_current_user)],
    config: Annotated[PipelineConfig, Depends(resolve_config)],
):
    # TODO: make this SSE
    if SESSION_DIR is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="SESSION_DIR not set")

    user_id = current_user.user_id
    user_path = Path(SESSION_DIR) / user_id
    history_db_path = user_path / f"{user_id}.sqlite"
    
    if not history_db_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    # Connect to repositories
    history_db = sqlite3.connect(history_db_path)
    history_repo = SqliteEventRepository(history_db)
    session_repo = SqliteSessionRepository(history_db)
    
    # Save user message
    user_event = Event(
        session_id=session_id,
        event_type=EventType.USER_MESSAGE,
        content=body.message
    )
    history_repo.save(user_event)

    # Initialize Vector Store (LanceDB)
    vector_stores = await get_or_create_vector_stores(user_path, username=user_id)

    recent_events = history_repo.get_recent(session_id, 1000)
    # Events are returned in DESC order, we need them in ASC order for context
    messages = [e.to_chat_message() for e in reversed(recent_events)]

    # Prepare tools
    # We add knowledge tools specifically for the chat agent
    knowledge_tools = [
        get_relevant_facts_tool(
            session_id=UUID(session_id),
            knowledge_store=vector_stores.knowledge_store,
            embedder=config.embedder or (lambda: FastembedTextEmbedder("sentence-transformers/all-MiniLM-L6-v2"))
        )
    ]
    
    # Instantiate Agent
    callback_factory = StreamCallbackFactory(session_id=session_id, history=history_repo)
    
    agent = Agent(
        chat_generator=config.model,
        system_prompt="You are now an expert security auditor in an interactive chat session. Use your tools to answer questions about the previously analyzed document and discovered vulnerabilities.",
        tools=cast(list[Tool], config.tools) + knowledge_tools,
        streaming_callback=callback_factory(),
    )

    # Run agent
    try:
        response = agent.run(messages=[*messages, ChatMessage.from_user(body.message)])
        callback_factory.flush()
        return {"response": response.get("last_message", "")}
    except Exception as e:
        import logging
        logging.error(f"Agent error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    finally:
        history_db.close()
