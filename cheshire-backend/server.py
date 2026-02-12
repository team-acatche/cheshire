from typing import Annotated
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File

load_dotenv()

api = FastAPI()

@api.post("/evaluate")
async def evaluate_document(
    document: Annotated[UploadFile, File(description="The document to be evaluated")],
):
    # TODO: Implement document evaluation
    return {"message": f"{document.filename} evaluated successfully"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(api, port=8000)