import logging
import os
import tempfile
from typing import Annotated
from pathlib import Path

import aiofiles
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.pipeline.vlm_pipeline import VlmPipeline
from docling.chunking import HybridChunker
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, granite_picture_description
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import Field
from dataclasses import dataclass

from model import evaluate_file
from tools.helpers.output_schema import VulnerabilityDetails

load_dotenv()

api = FastAPI()
logger = logging.getLogger("uvicorn.error")

api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

pdfconfig = PdfPipelineOptions()
pdfconfig.do_picture_description = True
pdfconfig.picture_description_options = granite_picture_description
pdfconfig.picture_description_options.prompt = "Describe the image in three sentences. Be concise and accurate."
pdfconfig.generate_picture_images = True

converter = DocumentConverter(
    format_options={
        InputFormat.PDF: PdfFormatOption(
            pipeline_options=pdfconfig
        )
    }
)

@api.post("/evaluate")
async def evaluate_document(
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

    if results := await evaluate_file(Path(document_path)):
        return results
    else:
        return []


@api.get("/healthcheck", status_code=200)
def healthcheck() -> str:
    return "Cheshire is running"


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(api, port=8000)
