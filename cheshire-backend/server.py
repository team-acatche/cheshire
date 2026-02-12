from fastapi import FastAPI

api = FastAPI()


@api.get("/")
def read_root() -> dict:
    return {"message": "Welcome to the Cheshire Backend API!"}


@api.get("/healthcheck", status_code=200)
def healthcheck() -> str:
    return "Cheshire is running"


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(api, port=8000)
