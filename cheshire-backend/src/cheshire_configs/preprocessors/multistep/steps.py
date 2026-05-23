from haystack import Pipeline

from cheshire_configs.preprocessors.multistep.pipelines import build_preprocessing_pipeline, build_evaluation_pipeline
from cheshire_configs.preprocessors.multistep.helpers import EvaluationChunk

from cheshire_configs.preprocessors.multistep.pipelines import build_synthesis_pipeline
from tools.helpers.output_schema import VulnerabilityDetails

import logging
logger = logging.getLogger("uvicorn.error")

def run_pass1(pdf_path: str) -> tuple[list[dict], dict]:
    preprocessing_pipeline: Pipeline = build_preprocessing_pipeline()
    evaluation_pipeline: Pipeline = build_evaluation_pipeline()

    logger.info("[1/2] Preprocessing document with Docling...")
    prep_result = preprocessing_pipeline.run({
        "docling_converter": {"pdf_path": pdf_path}
    })
    chunks: list[EvaluationChunk] = prep_result["docling_converter"]["chunks"]
    document_index: dict = prep_result["docling_converter"]["document_index"]
    logger.info(
        f"      {len(chunks)} chunks, "
        f"{len(document_index['sections'])} sections, "
        f"{len(document_index['figures'])} figures."
    )

    from cheshire_configs.preprocessors.multistep.tools import set_chunks_cache
    set_chunks_cache(chunks)

    logger.info("[2/2] Evaluating sections...")
    all_vulnerabilities: list[VulnerabilityDetails] = []

    for i, chunk in enumerate(chunks):
        logger.info(
            f"  [{i + 1}/{len(chunks)}] {chunk.heading} "
            f"(p{chunk.page_range[0]}-{chunk.page_range[1]}, "
            f"{len(chunk.figures)} figure(s))..."
        )

        previous_findings = [
            {
                "title": v.title,
                "description": v.description,
                "page_no": v.page_no
            }
            for v in all_vulnerabilities
        ]

        result = evaluation_pipeline.run({
            "chunk_message_builder": {
                "chunk": chunk,
                "document_index": document_index,
                "previous_findings": previous_findings
            },
            "findings_parser": {
                "chunk": chunk
            }
        })

        vulns: list[VulnerabilityDetails] = result["findings_parser"]["vulnerabilities"]
        all_vulnerabilities.extend(vulns)
        logger.info(f"      → {len(vulns)} vulnerability(ies).")

    return all_vulnerabilities, document_index

def run_pass2(all_findings: list, document_index: dict) -> list[VulnerabilityDetails]:
    logger.info("[Pass 2] Deduplicating and synthesising...")

    pipeline: Pipeline = build_synthesis_pipeline()

    result = pipeline.run({
        "synthesis_message_builder": {
            "all_findings": all_findings,
            "document_index": document_index
        }
    })

    final: list[VulnerabilityDetails] = result["synthesis_parser"]["vulnerabilities"]
    logger.info(f"  {len(all_findings)} → {len(final)} after deduplication.")

    return final