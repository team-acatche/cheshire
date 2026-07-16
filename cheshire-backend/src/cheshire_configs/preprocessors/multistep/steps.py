from dataclasses import dataclass

from haystack import Pipeline

from cheshire_configs.preprocessors.multistep.pipelines import build_preprocessing_pipeline, build_evaluation_pipeline
from cheshire_configs.preprocessors.multistep.helpers import EvaluationChunk, LocalFinding

from cheshire_configs.preprocessors.multistep.pipelines import build_synthesis_pipeline
from tools.helpers.output_schema import VulnerabilityDetails
from docling_core.types.doc import BoundingBox

import logging
logger = logging.getLogger("uvicorn.error")


@dataclass(frozen=True, kw_only=True)
class PreprocessingPassResults:
    findings: list[LocalFinding]
    document_index: dict
    chunks: list[EvaluationChunk]


def run_pass1(pdf_path: str) -> tuple[list[LocalFinding], dict]:
    preprocessing_pipeline: Pipeline = build_preprocessing_pipeline()

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

    evaluation_pipeline: Pipeline = build_evaluation_pipeline()

    logger.info("[2/2] Evaluating sections...")
    all_findings: list[LocalFinding] = []

    for i, chunk in enumerate(chunks):
        logger.info(
            f"  [{i + 1}/{len(chunks)}] {chunk.heading} "
            f"(p{chunk.page_range[0]}-{chunk.page_range[1]}, "
            f"{len(chunk.figures)} figure(s))..."
        )

        previous_findings = [
            {
                "finding": f.finding,
                "standard_ref": f.standard_ref,
                "severity": f.severity,
                "element_id": f.element_id,
                "figure_id": f.figure_id
            }
            for f in all_findings
        ]

        result = evaluation_pipeline.run({
            "chunk_message_builder": {
                "chunk": chunk,
                "document_index": document_index,
                "previous_findings": previous_findings
            },
            "agent": {
                "chunks_cache": chunks
            }
        })

        # findings recorded via add_local_finding tool
        state_findings: list[LocalFinding] = (
            result.get("agent", {}).get("findings_list") or []
        )

        all_findings.extend(state_findings)
        logger.info(
            f"      to {len(state_findings)} finding(s) recorded."
        )

    return PreprocessingPassResults(
        findings=all_findings,
        document_index=document_index,
        chunks=chunks
    )

def run_pass2(results: PreprocessingPassResults) -> list[VulnerabilityDetails]:
    logger.info("[Pass 2] Deduplicating and synthesising...")

    pipeline: Pipeline = build_synthesis_pipeline()

    result = pipeline.run({
        "synthesis_message_builder": {
            "all_findings": all_findings,
            "document_index": document_index
        }
    })

    # Read accepted findings from Agent state
    accepted_local: list[LocalFinding] = (
        result.get("agent", {}).get("accepted_findings") or []
    )
    contradictions = result.get("agent", {}).get("contradictions") or []

    logger.info(f"  {len(all_findings)} to {len(accepted_local)} after deduplication.")
    if contradictions:
        logger.info(f"  {len(contradictions)} contradiction(s) flagged:")
        for c in contradictions:
            logger.info(f"    - \"{c.finding_a_title}\" vs \"{c.finding_b_title}\": {c.description}")

    # Safeguard: if synthesis dropped all findings, fall back to programmatic dedup
    if len(accepted_local) == 0 and len(all_findings) > 0:
        logger.warning(
            f"Synthesis returned 0 findings from {len(all_findings)} inputs. "
            f"Falling back to programmatic deduplication."
        )
        seen = set()
        deduped = []
        for f in all_findings:
            # support both dataclass and dict
            element_id = getattr(f, "element_id", None) or (f.get("element_id") if isinstance(f, dict) else None)
            figure_id = getattr(f, "figure_id", None) or (f.get("figure_id") if isinstance(f, dict) else None)
            finding = getattr(f, "finding", None) or (f.get("finding") if isinstance(f, dict) else None) or ""
            key = (element_id, figure_id, finding)
            if key not in seen:
                deduped.append(f)
                seen.add(key)
        accepted_local = deduped
        logger.info(f"  Programmatic dedup: {len(all_findings)} to {len(accepted_local)}.")

    element_by_id = {}
    figure_by_id = {}
    for chunk in results.chunks:
        for e in chunk.element_refs:
            element_by_id[e.element_id] = e
        for fig in chunk.figures:
            figure_by_id[fig.figure_id] = fig

    final_vulnerabilities: list[VulnerabilityDetails] = []
    for f in accepted_local:
        element_id = getattr(f, "element_id", None) or (f.get("element_id") if isinstance(f, dict) else None)
        figure_id = getattr(f, "figure_id", None) or (f.get("figure_id") if isinstance(f, dict) else None)
        sub_bbox = getattr(f, "sub_bbox", None) or (f.get("sub_bbox") if isinstance(f, dict) else None)
        finding = getattr(f, "finding", None) or (f.get("finding") if isinstance(f, dict) else None) or ""
        title = getattr(f, "title", None) or (f.get("title") if isinstance(f, dict) else None)
        web_refs = getattr(f, "web_references", None) or (f.get("web_references") if isinstance(f, dict) else None) or []
        recs = getattr(f, "recommendations", None) or (f.get("recommendations") if isinstance(f, dict) else None) or []

        page_no = 1
        bbox = BoundingBox(l=0, t=0, r=0, b=0)

        if figure_id and figure_id in figure_by_id:
            fig = figure_by_id[figure_id]
            page_no = fig.page_number

            if sub_bbox and len(sub_bbox) == 4:
                sx1, sy1, sx2, sy2 = sub_bbox
                max_coord = max(sx1, sy1, sx2, sy2)
                scale_factor = 1.0 if (0.0 < max_coord <= 1.0) else 1000.0

                frac_x1 = max(0.0, min(1.0, sx1 / scale_factor))
                frac_y1 = max(0.0, min(1.0, sy1 / scale_factor))
                frac_x2 = max(0.0, min(1.0, sx2 / scale_factor))
                frac_y2 = max(0.0, min(1.0, sy2 / scale_factor))

                fig_w = fig.bbox_pdf.r - fig.bbox_pdf.l
                fig_h = fig.bbox_pdf.t - fig.bbox_pdf.b

                bbox = BoundingBox(
                    l=fig.bbox_pdf.l + frac_x1 * fig_w,
                    t=fig.bbox_pdf.t - frac_y1 * fig_h,
                    r=fig.bbox_pdf.l + frac_x2 * fig_w,
                    b=fig.bbox_pdf.t - frac_y2 * fig_h
                )
            else:
                bbox = fig.bbox_pdf

        elif element_id and element_id in element_by_id:
            elem = element_by_id[element_id]
            page_no = elem.page_number
            bbox = elem.bbox_pdf

        final_title = title if title else (finding[:60] + "..." if len(finding) > 60 else finding)
        final_vulnerabilities.append(
            VulnerabilityDetails(
                title=final_title,
                description=finding,
                page_no=page_no,
                bbox=bbox,
                web_references=web_refs,
                recommendations=recs
            )
        )

    return final_vulnerabilities