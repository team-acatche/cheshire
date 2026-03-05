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
from pydantic import Field
from dataclasses import dataclass

from model import evaluate_file
from tools.helpers.output_schema import VulnerabilityDetails
from tools.tools import query_document_tool, add_vulnerability_tool, read_vulnerabilities_tool
from tools.exa import web_search
from haystack.core.pipeline import Pipeline
from haystack.components.embedders.types import TextEmbedder

load_dotenv()

api = FastAPI()
logger = logging.getLogger("uvicorn.error")

# TODO (refactor): try making this a server state or something that isn't created with every request
# probably a DI container-like thing?
document_store = InMemoryDocumentStore(embedding_similarity_function="cosine")

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

    # TODO (bug, refactor): calling the endpoint results in creating new instances of these every time.
    # also DI?
    model = OllamaChatGenerator(
    	model=os.getenv("OLLAMA_CHAT_MODEL", "llama3.2"),
    	url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
    	generation_kwargs={
    		"num_ctx": 2**14,
    		# Qwen 3
    		"temperature": 0.6,
    		"top_p": 0.95,
    		"top_k": 20,
    		"min_p": 0,
    	},
    	think=True,
    )

    # TODO (bug, refactor): the retrieval pipeline should NOT be here.
    # also DI?
    embedder = OllamaTextEmbedder(
        model=os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text"),
        url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
    )
    retriever = InMemoryEmbeddingRetriever(document_store)
    rag_query_pipeline = Pipeline()
    rag_query_pipeline.add_component("embedder", embedder)
    rag_query_pipeline.add_component("retriever", retriever)
    rag_query_pipeline.connect("embedder.documents", "retriever")

    tools = [
		query_document_tool(rag_query_pipeline),
		web_search,
		add_vulnerability_tool("vulnerabilities_list"),
		read_vulnerabilities_tool("vulnerabilities_list")
	]

    # TODO (bug, refactor): the arguments to evaluate_file should be an external dependency
    if results := await evaluate_file(Path(document_path), model=model, tools=tools, preprocessor=ollama_rag_preprocessor(document_store)):
        return results
    else:
        return []


@api.get("/healthcheck", status_code=200)
def healthcheck() -> str:
    return "Cheshire is running"


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(api, port=8000)
