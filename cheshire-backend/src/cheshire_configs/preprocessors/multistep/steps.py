from haystack import Pipeline

from cheshire_configs.preprocessors.multistep.pipelines import build_preprocessing_pipeline, build_evaluation_pipeline
from cheshire_configs.preprocessors.multistep.helpers import EvaluationChunk

import logging
logger = logging.getLogger("uvicorn.error")

def run_pass1(pdf_path: str) -> tuple[list[dict], dict]:
    """
    Runs preprocessing and section evaluation.
    Returns (all_findings, document_index).
    """

    preprocessing_pipeline: Pipeline = build_preprocessing_pipeline()
    evaluation_pipeline: Pipeline = build_evaluation_pipeline()

    logger.info("[1/2] Preprocessing document with Docling...")

    prep_result = preprocessing_pipeline.run({
        "docling_converter": {
            "pdf_path": pdf_path
        }
    })

    chunks: list[EvaluationChunk] = prep_result["docling_converter"]["chunks"]
    document_index: dict = prep_result["docling_converter"]["document_index"]

    logger.info(
        f"{len(chunks)} chunks, "
        f"{len(document_index['sections'])} sections, "
        f"{len(document_index['figures'])} figures."
    )

    logger.info("[2/2] Evaluating sections...")

    all_findings: list[dict] = []

    for i, chunk in enumerate(chunks):
        logger.info(
            f"  [{i + 1}/{len(chunks)}] {chunk.heading} "
            f"(p{chunk.page_range[0]}-{chunk.page_range[1]}, "
            f"{len(chunk.figures)} figure(s))..."
        )

        result = evaluation_pipeline.run({
            "chunk_message_builder": {
                "chunk": chunk,
                "document_index": document_index
            },
            "findings_parser": {
                "chunk_id": chunk.chunk_id,
                "chunk_heading": chunk.heading
            }
        })

        findings: list[dict] = result["findings_parser"]["findings"]
        all_findings.extend(findings)

        error_count = sum(1 for f in findings if "error" in f)
        ok_count = len(findings) - error_count
        logger.info(f"{ok_count} finding(s)")
        if error_count:
            logger.info(f", {error_count} parse error(s)")

    return all_findings, document_index