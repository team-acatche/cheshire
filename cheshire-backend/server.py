from fastapi import FastAPI

api = FastAPI()


@api.get("/")
def read_root() -> dict:
    return {"message": "Welcome to the Cheshire Backend API!"}


@api.get("/hello_world")
def hello_world() -> dict:
    return {"Hello": "World"}


@api.get("/hello/{name}")
def hello_name(name: str) -> dict:
    return {"Hello": name}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(api, port=8000)
