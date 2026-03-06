import os
import tempfile
from pathlib import Path
from typing import Annotated
import aiofiles
import logging
from fastapi import APIRouter, Depends, UploadFile, File

from model import evaluate_file
from tools.helpers.output_schema import VulnerabilityDetails
from cheshire_configs.ollama.rag_config import ollama_rag_config

router = APIRouter(
    prefix="/rag/ollama",
    tags=["rag", "ollama"],
)
logger = logging.getLogger("uvicorn.error")

@router.post("/evaluate")
async def evaluate_document(
    config: Annotated[dict, Depends(ollama_rag_config)],
    uploaded_document: Annotated[UploadFile, File(description="The document to be evaluated")],
) -> list[VulnerabilityDetails]:
    # Save the uploaded document
    temp_dir = tempfile.mkdtemp()
    filename = uploaded_document.filename or "upload"
    document_path = os.path.join(temp_dir, filename)

    logger.info(f"save({filename}): Saving {filename} to {document_path}...")
    async with aiofiles.open(document_path, "wb") as d:
        await d.write(await uploaded_document.read())
    logger.info(f"save({filename}): {document_path} saved.")

    if results := await evaluate_file(Path(document_path),
                                        model=config["model"],
                                        tools=config["tools"],
                                        document_store=config["document_store"],
                                        document_preprocessor=config["document_preprocessor"]
    ):
        return results
    else:
        return []
