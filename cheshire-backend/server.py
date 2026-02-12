from fastapi import FastAPI

api = FastAPI()


@api.get("/healthcheck", status_code=200)
def healthcheck() -> str:
    return "Cheshire is running"


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(api, port=8000)
