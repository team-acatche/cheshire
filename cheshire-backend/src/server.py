import logging

from dotenv import load_dotenv
load_dotenv()

from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends

from cheshire_configs.registry import configs
from endpoints.evaluate import evaluate_router

api = FastAPI(dependencies=[Depends(configs)])
logger = logging.getLogger("uvicorn.error")

api.include_router(
    evaluate_router,
    prefix="/api/v1",
)

@api.get("/healthcheck", status_code=200)
def healthcheck() -> str:
    return "Cheshire is running"


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(api, port=8000)
