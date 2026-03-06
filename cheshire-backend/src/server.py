import logging

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
import endpoints

api = FastAPI()
logger = logging.getLogger("uvicorn.error")

api.include_router(
    endpoints.rag.ollama.router,
    prefix="/api/v1",
)

@api.get("/healthcheck", status_code=200)
def healthcheck() -> str:
    return "Cheshire is running"


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(api, port=8000)
