import os
import tempfile
from pathlib import Path
from typing import Annotated, Literal
import aiofiles
import logging
from fastapi import APIRouter, Depends, UploadFile, File
from pydantic import Field

from model import evaluate_file
from tools.helpers.output_schema import VulnerabilityDetails
from cheshire_configs.core import PipelineConfig
from cheshire_configs.resolver import resolve_config

evaluate_router = APIRouter()
logger = logging.getLogger("uvicorn.error")

@evaluate_router.post("/evaluate")
async def evaluate_document(
    config: Annotated[PipelineConfig, Depends(resolve_config)],
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

    if results := await evaluate_file(Path(document_path), config):
        return results
    else:
        return []
