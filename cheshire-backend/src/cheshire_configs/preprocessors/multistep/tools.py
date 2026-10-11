import json
from typing import Annotated, Any
from haystack.tools import tool
from knowledge_base.repository import KnowledgeRepository
from cheshire_configs.preprocessors.multistep.helpers import LocalFinding, EvaluationChunk


from globals import DATA_PATH
from knowledge_base.qdrant import QdrantRepositoryManager

@tool
def get_standard(
    query: Annotated[str, "The query to search for company security requirements (e.g. 'password hashing', 'session management')."]
) -> dict[str, Any]:
    """
    Search the company's internal security standards for relevant requirements.
    Results are company-specific guidelines — reference them as "company standard"
    in findings, not by external framework names.

    :param query: the query to search for relevant company requirements.

    :return: a dict containing company standard requirements relevant to the query.
    """
    knowledge_repo: KnowledgeRepository
    _, knowledge_repo = QdrantRepositoryManager.get_repositories(DATA_PATH)
    results = knowledge_repo.search(query=query)
    facts: list[str] = [f"[Company standard requirement] {document.content}" for document in results]
    return {"facts": facts}

@tool
def query_other_section(
    section_title: Annotated[str, "The title or heading of the section to query (e.g. 'Authentication', 'Section 5')."],
    chunks_cache: list[EvaluationChunk],
) -> str:
    """
    Retrieves the full text of another section in the document by title search.
    Use this when you see a reference to another section or component that is not
    fully detailed in the current section text.

    :param section_title: the title or heading of the section to retrieve.
    :return: the text of the matching section, or a warning if not found.
    """
        
    matches = []
    for chunk in chunks_cache:
        if section_title.lower() in chunk.heading.lower():
            matches.append(
                f"--- Section: {chunk.heading} (pages {chunk.page_range[0]}-{chunk.page_range[1]}) ---\n"
                f"{chunk.structured_text}"
            )
            
    if matches:
        return "\n\n".join(matches)
        
    return f"Warning: No sections found matching title '{section_title}'."

def add_local_finding(
    finding: LocalFinding | dict | str,
    element_type: str | None = None,
    standard_ref: str | None = None,
    severity: str | None = None,
    confidence: float | None = None,
    element_id: list[str] | str | None = None,
    figure_id: str | None = None,
    sub_bbox: list[list[float]] | list[float] | None = None,
    title: str | None = None,
    web_references: list[str] | None = None,
    recommendations: list[str] | None = None,
) -> dict:
    """
    Record a local finding gap/vulnerability.

    :param finding: The finding details matching the LocalFinding schema.
    """
    if isinstance(finding, str) and (element_type is not None or standard_ref is not None or severity is not None):
        finding_dict = {
            "finding": finding,
            "element_type": element_type or "paragraph",
            "standard_ref": standard_ref or "",
            "severity": severity or "observation",
            "confidence": confidence if confidence is not None else 1.0,
            "element_id": element_id,
            "figure_id": figure_id,
            "sub_bbox": sub_bbox,
            "title": title,
            "web_references": web_references or [],
            "recommendations": recommendations or []
        }
        _finding = LocalFinding.model_validate(finding_dict)
    elif isinstance(finding, str):
        try:
            _finding = LocalFinding.model_validate_json(finding)
        except Exception:
            _finding = LocalFinding(
                finding=finding,
                element_type=element_type or "paragraph",
                standard_ref=standard_ref or "",
                severity=severity or "observation",
                confidence=confidence if confidence is not None else 1.0,
                element_id=element_id,
                figure_id=figure_id,
                sub_bbox=sub_bbox,
                title=title,
                web_references=web_references or [],
                recommendations=recommendations or []
            )
    elif isinstance(finding, dict):
        _finding = LocalFinding.model_validate(finding)
    else:
        _finding = finding
    return {"finding": _finding}

def accept_local_finding(
    finding: LocalFinding | dict | str,
    element_type: str | None = None,
    standard_ref: str | None = None,
    severity: str | None = None,
    confidence: float | None = None,
    element_id: list[str] | str | None = None,
    figure_id: str | None = None,
    sub_bbox: list[list[float]] | list[float] | None = None,
    title: str | None = None,
    web_references: list[str] | None = None,
    recommendations: list[str] | None = None,
) -> dict:
    """
    Accept a local finding as valid and non-duplicate. Call this for each unique local finding you want to keep.

    :param finding: The local finding to accept. Must match the LocalFinding schema.
    """
    if isinstance(finding, str) and (element_type is not None or standard_ref is not None or severity is not None):
        finding_dict = {
            "finding": finding,
            "element_type": element_type or "paragraph",
            "standard_ref": standard_ref or "",
            "severity": severity or "observation",
            "confidence": confidence if confidence is not None else 1.0,
            "element_id": element_id,
            "figure_id": figure_id,
            "sub_bbox": sub_bbox,
            "title": title,
            "web_references": web_references or [],
            "recommendations": recommendations or []
        }
        _finding = LocalFinding.model_validate(finding_dict)
    elif isinstance(finding, str):
        try:
            _finding = LocalFinding.model_validate_json(finding)
        except Exception:
            _finding = LocalFinding(
                finding=finding,
                element_type=element_type or "paragraph",
                standard_ref=standard_ref or "",
                severity=severity or "observation",
                confidence=confidence if confidence is not None else 1.0,
                element_id=element_id,
                figure_id=figure_id,
                sub_bbox=sub_bbox,
                title=title,
                web_references=web_references or [],
                recommendations=recommendations or []
            )
    elif isinstance(finding, dict):
        _finding = LocalFinding.model_validate(finding)
    else:
        _finding = finding
    return {"finding": _finding}

SEVERITY_ORDER = {
    "critical": 5,
    "high": 4,
    "medium": 3,
    "low": 2,
    "observation": 1,
}

def merge_findings(
    findings: list[LocalFinding | dict | str] | None = None,
    title: str | None = None,
    finding: str | None = None,
    element_type: str | None = None,
    standard_ref: str | None = None,
    severity: str | None = None,
    confidence: float | None = None,
    element_id: list[str] | str | None = None,
    figure_id: str | None = None,
    sub_bbox: list[list[float]] | list[float] | None = None,
    web_references: list[str] | None = None,
    recommendations: list[str] | None = None,
    all_findings_cache: list[LocalFinding | dict] | None = None,
) -> dict:
    """
    Combine multiple same-topic findings into one, aggregating each duplicate's unique fields
    (such as element_id, sub_bbox, etc.) into a list, and summarizing their titles and descriptions
    into a single finding.

    :param findings: List of duplicate findings (LocalFinding instances, dicts, or titles).
    :param title: The summarized short title representing the combined finding.
    :param finding: The summarized description of the combined vulnerability.
    """
    if isinstance(findings, str):
        findings_str = findings.strip()
        if findings_str.startswith("["):
            try:
                findings = json.loads(findings_str)
            except Exception:
                findings = [findings_str]
        elif findings_str.startswith("{"):
            try:
                findings = [json.loads(findings_str)]
            except Exception:
                findings = [findings_str]
        else:
            findings = [findings_str]
    elif findings is not None and not isinstance(findings, list):
        findings = [findings]
    elif findings is None:
        findings = []

    normalized_findings: list[LocalFinding | dict] = []
    for item in findings:
        if isinstance(item, str):
            item_str = item.strip()
            if item_str.startswith("{"):
                try:
                    normalized_findings.append(LocalFinding.model_validate_json(item_str))
                    continue
                except Exception:
                    pass
            if all_findings_cache:
                matched = False
                for cached in all_findings_cache:
                    cached_title = getattr(cached, "title", None) or (cached.get("title") if isinstance(cached, dict) else None)
                    if cached_title and cached_title.strip().lower() == item_str.lower():
                        normalized_findings.append(cached)
                        matched = True
                        break
                if matched:
                    continue
            normalized_findings.append({"title": item_str, "finding": item_str})
        elif isinstance(item, (LocalFinding, dict)):
            normalized_findings.append(item)

    # 1. element_id aggregation
    collected_element_ids: list[str] = []
    for item in normalized_findings:
        eid = getattr(item, "element_id", None) or (item.get("element_id") if isinstance(item, dict) else None)
        if isinstance(eid, list):
            for e in eid:
                if e and str(e) not in collected_element_ids:
                    collected_element_ids.append(str(e))
        elif isinstance(eid, str) and eid.strip():
            if eid.strip() not in collected_element_ids:
                collected_element_ids.append(eid.strip())
    if element_id:
        if isinstance(element_id, list):
            for e in element_id:
                if e and str(e) not in collected_element_ids:
                    collected_element_ids.append(str(e))
        elif isinstance(element_id, str) and element_id.strip():
            if element_id.strip() not in collected_element_ids:
                collected_element_ids.append(element_id.strip())

    # 2. sub_bbox aggregation
    collected_sub_bboxes: list[list[float]] = []
    def _add_boxes(raw):
        if not raw:
            return
        if isinstance(raw, list):
            if len(raw) == 4 and all(isinstance(x, (int, float)) for x in raw):
                box = [float(x) for x in raw]
                if box not in collected_sub_bboxes:
                    collected_sub_bboxes.append(box)
            else:
                for b in raw:
                    if isinstance(b, (list, tuple)) and len(b) == 4 and all(isinstance(x, (int, float)) for x in b):
                        box = [float(x) for x in b]
                        if box not in collected_sub_bboxes:
                            collected_sub_bboxes.append(box)

    for item in normalized_findings:
        sb = getattr(item, "sub_bbox", None) or (item.get("sub_bbox") if isinstance(item, dict) else None)
        _add_boxes(sb)
    _add_boxes(sub_bbox)

    # 3. figure_id
    chosen_figure_id = figure_id
    if not chosen_figure_id:
        for item in normalized_findings:
            fid = getattr(item, "figure_id", None) or (item.get("figure_id") if isinstance(item, dict) else None)
            if fid:
                chosen_figure_id = fid
                break

    # 4. element_type
    chosen_element_type = element_type
    if not chosen_element_type:
        for item in normalized_findings:
            et = getattr(item, "element_type", None) or (item.get("element_type") if isinstance(item, dict) else None)
            if et:
                chosen_element_type = et
                break
    if not chosen_element_type:
        chosen_element_type = "diagram_node" if chosen_figure_id else "paragraph"

    # 5. standard_ref
    chosen_standard_ref = standard_ref
    if not chosen_standard_ref:
        for item in normalized_findings:
            sr = getattr(item, "standard_ref", None) or (item.get("standard_ref") if isinstance(item, dict) else None)
            if sr:
                chosen_standard_ref = sr
                break
    chosen_standard_ref = chosen_standard_ref or ""

    # 6. severity
    chosen_severity = (severity or "").lower()
    best_rank = SEVERITY_ORDER.get(chosen_severity, 0)
    best_sev_name = chosen_severity if best_rank > 0 else "observation"
    for item in normalized_findings:
        s = getattr(item, "severity", None) or (item.get("severity") if isinstance(item, dict) else None)
        if s and isinstance(s, str):
            s_lower = s.strip().lower()
            rank = SEVERITY_ORDER.get(s_lower, 0)
            if rank > best_rank:
                best_rank = rank
                best_sev_name = s_lower

    # 7. confidence
    max_confidence = confidence if confidence is not None else 0.0
    for item in normalized_findings:
        c = getattr(item, "confidence", None) or (item.get("confidence") if isinstance(item, dict) else None)
        if c is not None and isinstance(c, (int, float)):
            max_confidence = max(max_confidence, float(c))
    if max_confidence <= 0.0:
        max_confidence = 1.0

    # 8. web_references
    collected_web_refs: list[str] = []
    for item in normalized_findings:
        wr = getattr(item, "web_references", None) or (item.get("web_references") if isinstance(item, dict) else None)
        if isinstance(wr, list):
            for url in wr:
                if url and str(url) not in collected_web_refs:
                    collected_web_refs.append(str(url))
    if web_references:
        for url in web_references:
            if url and str(url) not in collected_web_refs:
                collected_web_refs.append(str(url))

    # 9. recommendations
    collected_recs: list[str] = []
    for item in normalized_findings:
        recs = getattr(item, "recommendations", None) or (item.get("recommendations") if isinstance(item, dict) else None)
        if isinstance(recs, list):
            for r in recs:
                if r and str(r) not in collected_recs:
                    collected_recs.append(str(r))
    if recommendations:
        for r in recommendations:
            if r and str(r) not in collected_recs:
                collected_recs.append(str(r))

    # 10. title & finding (description)
    chosen_title = title
    if not chosen_title:
        for item in normalized_findings:
            t = getattr(item, "title", None) or (item.get("title") if isinstance(item, dict) else None)
            if t:
                chosen_title = t
                break

    chosen_finding = finding
    if not chosen_finding:
        desc_parts = []
        for item in normalized_findings:
            d = getattr(item, "finding", None) or (item.get("finding") if isinstance(item, dict) else None)
            if d and d not in desc_parts:
                desc_parts.append(d)
        chosen_finding = " ".join(desc_parts) if desc_parts else (chosen_title or "")

    _merged = LocalFinding(
        element_id=collected_element_ids if collected_element_ids else None,
        figure_id=chosen_figure_id,
        sub_bbox=collected_sub_bboxes if collected_sub_bboxes else None,
        element_type=chosen_element_type,
        finding=chosen_finding,
        standard_ref=chosen_standard_ref,
        severity=best_sev_name,
        confidence=min(1.0, max(0.0, max_confidence)),
        title=chosen_title,
        web_references=collected_web_refs,
        recommendations=collected_recs,
    )
    return {"finding": _merged}


