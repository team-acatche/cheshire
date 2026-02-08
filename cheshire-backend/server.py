from fastapi import FastAPI

api = FastAPI()

@api.get("/hello_world")
def hello_world():
    return {"Hello": "World"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(api, port=8000)