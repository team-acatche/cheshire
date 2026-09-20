import logging
import os

from dotenv import load_dotenv
load_dotenv()

from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, status
from fastapi.middleware.cors import CORSMiddleware

from cheshire_configs.registry import configs
from endpoints.evaluate import evaluate_router
from endpoints.chat import chat_router
from endpoints.user_auth import auth_router
from endpoints.user import user_router

from globals import DATA_PATH, SESSIONS_PATH, STANDARDS_DIR
from knowledge_base.seeder import seed_knowledge_base, extract_standards_from
from knowledge_base.qdrant import QdrantRepositoryManager

@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(DATA_PATH, exist_ok=True) # ensure that the DATA_PATH exists
    os.makedirs(SESSIONS_PATH, exist_ok=True) # ensure that the SESSIONS_PATH exists
    os.makedirs(STANDARDS_DIR, exist_ok=True) # ensure that the STANDARDS_DIR exists

    # seed the knowledge base with company standards
    _, knowledge_repo = QdrantRepositoryManager.get_repositories(DATA_PATH)
    for file_path in STANDARDS_DIR.glob("*.json"):
        standards = extract_standards_from(file_path)
        seed_knowledge_base(knowledge_repo, standards, source=file_path.name)
    yield

api = FastAPI(dependencies=[Depends(configs)], lifespan=lifespan)
api.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|cheshire-frontend|cheshire-backend)(:[0-9]+)?$",
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
logger = logging.getLogger("uvicorn.error")

api.include_router(
    auth_router,
    prefix="/api/v1",
)

api.include_router(
    evaluate_router,
    prefix="/api/v1",
)

api.include_router(
    user_router,
    prefix="/api/v1",
)

api.include_router(
    chat_router,
    prefix="/api/v1",
)

@api.get("/healthcheck", status_code=status.HTTP_200_OK)
def healthcheck() -> str:
    return "Cheshire is running"


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(api, port=8000)