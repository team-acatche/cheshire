from dataclasses import dataclass

from haystack import Pipeline

from cheshire_configs.preprocessors.multistep.pipelines import build_preprocessing_pipeline, build_evaluation_pipeline
from cheshire_configs.preprocessors.multistep.helpers import EvaluationChunk, LocalFinding, ElementRef, FigureRef
from cheshire_configs.preprocessors.multistep.components.findings_parser import clamp

from cheshire_configs.preprocessors.multistep.pipelines import build_dedup_pipeline, build_global_audit_pipeline
from tools.helpers.output_schema import PageBoundingBox, VulnerabilityDetails, Contradiction
from docling_core.types.doc import BoundingBox

import logging
from typing import Any, Optional
from knowledge_base.job_store import CancelCheck, raise_if_cancelled
from knowledge_base.progress import get_progress
from knowledge_base.repository import KnowledgeRepository
logger = logging.getLogger("uvicorn.error")


@dataclass(frozen=True, kw_only=True)
class PreprocessingPassResults:
    findings: list[LocalFinding]
    document_index: dict
    chunks: list[EvaluationChunk]


def run_pass1(
    pdf_path: str,
    should_cancel: Optional[CancelCheck] = None,
    knowledge_repo: Optional[KnowledgeRepository] = None,
) -> PreprocessingPassResults:
    raise_if_cancelled(should_cancel)
    progress = get_progress()
    progress.set_stage("parsing", "Reading the PDF layout, tables and diagrams…")

    preprocessing_pipeline: Pipeline = build_preprocessing_pipeline()

    logger.info("[1/2] Preprocessing document with Docling…")
    prep_result: dict = preprocessing_pipeline.run({
        "docling_converter": {"pdf_path": pdf_path}
    })
    raise_if_cancelled(should_cancel)
    chunks: list[EvaluationChunk] = prep_result["docling_converter"]["chunks"]
    document_index: dict = prep_result["docling_converter"]["document_index"]
    progress.set_document(
        page_count=max((c.page_range[1] for c in chunks), default=0),
        sections=len(document_index["sections"]),
        figures=len(document_index["figures"]),
    )
    progress.set_stage("auditing", f"Auditing {len(chunks)} sections against company standards…")
    logger.info(
        f"      {len(chunks)} chunks, "
        f"{len(document_index['sections'])} sections, "
        f"{len(document_index['figures'])} figures."
    )

    evaluation_pipeline: Pipeline = build_evaluation_pipeline(knowledge_repo=knowledge_repo)

    logger.info("[2/2] Evaluating sections...")
    all_findings: list[LocalFinding] = []

    for i, chunk in enumerate(chunks):
        raise_if_cancelled(should_cancel)
        progress.begin_chunk(i, len(chunks), chunk.heading, chunk.page_range, len(chunk.figures))
        i: int
        chunk: EvaluationChunk
        logger.info(
            f"  [{i + 1}/{len(chunks)}] {chunk.heading} "
            f"(p{chunk.page_range[0]}-{chunk.page_range[1]}, "
            f"{len(chunk.figures)} figure(s))..."
        )

        previous_findings: list[dict] = [
            {
                "finding": f.finding,
                "standard_ref": f.standard_ref,
                "severity": f.severity,
                "element_id": f.element_id,
                "figure_id": f.figure_id
            }
            for f in all_findings
        ]

        # evaluate chunk with retry
        max_chunk_retries = 2
        result: dict = {}
        for attempt in range(max_chunk_retries):
            try:
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
                break
            except EvaluationCancelled:
                raise
            except Exception as e:
                # retry chunk once on transient pipeline crash
                if attempt < max_chunk_retries - 1:
                    logger.warning(f"chunk {i + 1} attempt {attempt + 1} failed, retrying chunk: {e}")
                else:
                    logger.error(f"chunk {i + 1} failed after {max_chunk_retries} attempts: {e}")
                    raise

        # findings recorded via add_local_finding tool
        state_findings: list[LocalFinding] = (
            result.get("agent", {}).get("findings_list") or []
        )

        all_findings.extend(state_findings)
        progress.end_chunk(chunk.page_range, state_findings)
        logger.info(
            f"      to {len(state_findings)} finding(s) recorded."
        )

    return PreprocessingPassResults(
        findings=all_findings,
        document_index=document_index,
        chunks=chunks
    )

def run_pass2(
    results: PreprocessingPassResults,
    should_cancel: Optional[CancelCheck] = None,
    knowledge_repo: Optional[KnowledgeRepository] = None,
) -> list[VulnerabilityDetails]:
    progress = get_progress()
    all_findings: list[LocalFinding] = results.findings
    document_index: dict = results.document_index
    progress.set_stage("dedup", f"Merging duplicates across {len(all_findings)} findings…")

    # ---- Step 1: Deduplication & contradiction resolution ----
    raise_if_cancelled(should_cancel)
    logger.info("[Pass 2a] Deduplicating findings...")
    dedup_pipeline: Pipeline = build_dedup_pipeline()

    dedup_result: dict = dedup_pipeline.run({
        "dedup_message_builder": {
            "all_findings": all_findings,
        }
    })

    accepted_local: list[LocalFinding] = (
        dedup_result.get("agent", {}).get("accepted_findings") or []
    )
    contradictions: list[Contradiction] = (
        dedup_result.get("agent", {}).get("contradictions") or []
    )

    logger.info(f"  {len(all_findings)} to {len(accepted_local)} after deduplication.")
    if contradictions:
        logger.info(f"  {len(contradictions)} contradiction(s) flagged:")
        for c in contradictions:
            c: Contradiction
            logger.info(f"    - \"{c.finding_a_title}\" vs \"{c.finding_b_title}\": {c.description}")

    # Safeguard: if dedup dropped all findings, fall back to programmatic dedup
    if len(accepted_local) == 0 and len(all_findings) > 0:
        logger.warning(
            f"Dedup returned 0 findings from {len(all_findings)} inputs. "
            f"Falling back to programmatic deduplication."
        )
        seen: set[tuple[Any, Any, Any]] = set()
        deduped: list[LocalFinding] = []
        for f in all_findings:
            f: LocalFinding | dict
            # support both dataclass and dict
            elem_val = getattr(f, "element_id", None) or (f.get("element_id") if isinstance(f, dict) else None)
            elem_key = tuple(elem_val) if isinstance(elem_val, list) else elem_val
            figure_id: str | None = getattr(f, "figure_id", None) or (f.get("figure_id") if isinstance(f, dict) else None)
            finding: str = getattr(f, "finding", None) or (f.get("finding") if isinstance(f, dict) else None) or ""
            key: tuple[Any, str | None, str] = (elem_key, figure_id, finding)
            if key not in seen:
                deduped.append(f)
                seen.add(key)
        accepted_local = deduped
        progress.log("info", f"{len(all_findings)} findings → {len(accepted_local)} after merging")
        logger.info(f"  Programmatic dedup: {len(all_findings)} to {len(accepted_local)}.")

    # ---- Step 2: Global standards checklist audit (fresh context) ----
    raise_if_cancelled(should_cancel)
    progress.set_stage("global", "Checking required sections, diagrams and references…")
    logger.info("[Pass 2b] Global standards audit...")
    audit_pipeline: Pipeline = build_global_audit_pipeline(knowledge_repo=knowledge_repo)

    audit_result: dict = audit_pipeline.run({
        "global_audit_message_builder": {
            "document_index": document_index,
            "accepted_findings": accepted_local
        }
    })

    audit_findings: list[LocalFinding] = (
        audit_result.get("agent", {}).get("audit_findings") or []
    )
    logger.info(f"  {len(audit_findings)} global finding(s) recorded.")
    progress.log("info", f"{len(audit_findings)} document-wide finding(s) added")
    progress.set_stage("finalizing", "Locating findings on the page…")
    raise_if_cancelled(should_cancel)

    # Merge dedup-accepted findings with new global audit findings
    audit_ids = {id(f) for f in audit_findings}
    accepted_local = list(accepted_local) + audit_findings
    # reconstruct element and figure lookup for findings parsing
    element_by_id: dict[str, ElementRef] = {}
    figure_by_id: dict[str, FigureRef] = {}
    for chunk in results.chunks:
        chunk: EvaluationChunk
        for e in chunk.element_refs:
            e: ElementRef
            element_by_id[e.element_id] = e
        for fig in chunk.figures:
            fig: FigureRef
            figure_by_id[fig.figure_id] = fig

    final_vulnerabilities: list[VulnerabilityDetails] = []
    for f in accepted_local:
        f: LocalFinding | dict
        is_document: bool = id(f) in audit_ids

        element_id = getattr(f, "element_id", None) or (f.get("element_id") if isinstance(f, dict) else None)
        figure_id: str | None = getattr(f, "figure_id", None) or (f.get("figure_id") if isinstance(f, dict) else None)
        sub_bbox = getattr(f, "sub_bbox", None) or (f.get("sub_bbox") if isinstance(f, dict) else None)
        finding: str = getattr(f, "finding", None) or (f.get("finding") if isinstance(f, dict) else None) or ""
        title: str | None = getattr(f, "title", None) or (f.get("title") if isinstance(f, dict) else None)
        web_refs: list[str] = getattr(f, "web_references", None) or (f.get("web_references") if isinstance(f, dict) else None) or []
        recs: list[str] = getattr(f, "recommendations", None) or (f.get("recommendations") if isinstance(f, dict) else None) or []

        severity = getattr(f, "severity", None) or (f.get("severity") if isinstance(f, dict) else None)
        if severity not in ("major", "minor", "observation"):
            severity = "observation"
        confidence = getattr(f, "confidence", None)
        if confidence is None and isinstance(f, dict):
            confidence = f.get("confidence")
        if confidence is not None:
            confidence = min(1.0, max(0.0, float(confidence)))

        page_no: int = 1
        bboxes: list[PageBoundingBox] = []

        if is_document:
            pass

        elif figure_id and figure_id in figure_by_id:
            fig: FigureRef = figure_by_id[figure_id]
            page_no = fig.page_number
            origin = fig.bbox_pdf.coord_origin

            raw_boxes: list[list[float]] = []
            if isinstance(sub_bbox, list):
                if len(sub_bbox) == 4 and all(isinstance(x, (int, float)) for x in sub_bbox):
                    raw_boxes = [sub_bbox]
                else:
                    raw_boxes = [b for b in sub_bbox if isinstance(b, list) and len(b) == 4 and all(isinstance(x, (int, float)) for x in b)]

            fig_w: float = fig.bbox_pdf.r - fig.bbox_pdf.l
            fig_h: float = fig.bbox_pdf.t - fig.bbox_pdf.b

            for sb in raw_boxes:
                sx1, sy1, sx2, sy2 = sb
                max_coord: float = max(sx1, sy1, sx2, sy2)
                scale_factor: float = 1.0 if (0.0 < max_coord <= 1.0) else 1000.0

                frac_x1: float = clamp(0.0, sx1 / scale_factor, 1.0)
                frac_y1: float = clamp(0.0, sy1 / scale_factor, 1.0)
                frac_x2: float = clamp(0.0, sx2 / scale_factor, 1.0)
                frac_y2: float = clamp(0.0, sy2 / scale_factor, 1.0)

                bboxes.append(PageBoundingBox(
                    l=fig.bbox_pdf.l + frac_x1 * fig_w,
                    t=fig.bbox_pdf.t - frac_y1 * fig_h,
                    r=fig.bbox_pdf.l + frac_x2 * fig_w,
                    b=fig.bbox_pdf.t - frac_y2 * fig_h,
                    coord_origin=origin,
                    page_no=fig.page_number,
                ))

            if not bboxes:  # no usable sub_bbox: highlight the whole figure
                bboxes = [PageBoundingBox(**fig.bbox_pdf.model_dump(), page_no=fig.page_number)]

        elif element_id:
            elem_ids = [element_id] if isinstance(element_id, str) else element_id
            for eid in elem_ids:
                elem = element_by_id.get(eid)
                if elem:
                    bboxes.append(PageBoundingBox(**elem.bbox_pdf.model_dump(), page_no=elem.page_number))
            if bboxes:
                page_no = bboxes[0].page_no or 1  # finding.page_no = first box's page

        final_title: str = title if title else (finding[:60] + "..." if len(finding) > 60 else finding)
        final_vulnerabilities.append(
            VulnerabilityDetails(
                title=final_title,
                description=finding,
                page_no=page_no,
                bboxes=bboxes,  # bbox is derived from bboxes[0] by the validator
                web_references=web_refs,
                recommendations=recs,
                scope="section" if bboxes else "document",
                severity=severity,
                confidence=confidence,
            )
        )

    return final_vulnerabilities