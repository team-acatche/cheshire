from fastapi import FastAPI

api = FastAPI()

@api.get("/hello_world")
def hello_world():
    return {"Hello": "World"}

@api.post("/evaluate")
def evaluate_document():
    # TODO: Implement document evaluation
    return {"message": "Document evaluated successfully"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(api, port=8000)