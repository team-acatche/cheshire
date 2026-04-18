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
from auth.dependencies import SESSIONS_PATH

@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(SESSIONS_PATH, exist_ok=True) # ensure that the SESSION_DIR exists
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
    chat_router,
    prefix="/api/v1",
)

@api.get("/healthcheck", status_code=status.HTTP_200_OK)
def healthcheck() -> str:
    return "Cheshire is running"


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(api, port=8000)
