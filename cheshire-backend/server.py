from fastapi import FastAPI

api = FastAPI()


@api.get("/")
def read_root() -> dict:
    return {"message": "Welcome to the Cheshire Backend API!"}


@api.get("/healthcheck")
def healthcheck() -> dict:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(api, port=8000)
