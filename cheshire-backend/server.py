import logging
import os
import tempfile
from typing import Annotated

import aiofiles
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.pipeline.vlm_pipeline import VlmPipeline
from docling.chunking import HybridChunker
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, granite_picture_description
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File
from pydantic import Field
from dataclasses import dataclass

from document_source import DocumentSource

load_dotenv()

api = FastAPI()
logger = logging.getLogger("uvicorn.error")

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
) -> list[DocumentSource]:
    # Save the uploaded document
    temp_dir = tempfile.mkdtemp()
    filename = uploaded_document.filename or "upload"
    document_path = os.path.join(temp_dir, filename)

    logger.info(f"save({filename}): Saving {filename} to {document_path}...")
    async with aiofiles.open(document_path, "wb") as d:
        await d.write(await uploaded_document.read())
    logger.info(f"save({filename}): {document_path} saved.")

    # Process the saved document with Docling
    logger.info(f"process({filename}): Processing {filename} with Docling...")
    doc = converter.convert(document_path).document
    logger.info(f"process({filename}): {filename} processed.")

    # Save the figures
    logger.info(f"save({filename}): Saving figures from {filename}...")
    figures_saved: int = 0
    for figure in doc.pictures:
        assert figure.image is not None
        figure_path = os.path.join(temp_dir, f"{filename.split('.')[0]}__image{figures_saved}.png")
        if raw_image := figure.image.pil_image:
            logger.info(f"save({filename}): Saving {figure_path}...")
            raw_image.save(figure_path)
            logger.info(f"save({filename}): {figure_path} saved.")
            figures_saved += 1
    logger.info(f"save({filename}): {figures_saved} figures from {filename} saved.")

    return DocumentSource.from_docling_document(doc)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(api, port=8000)