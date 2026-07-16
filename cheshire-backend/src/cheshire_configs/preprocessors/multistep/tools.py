from typing import Annotated, Any
from haystack.tools import tool
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
    _, knowledge_repo = QdrantRepositoryManager.get_repositories(DATA_PATH, username="system")
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
    element_id: str | None = None,
    figure_id: str | None = None,
    sub_bbox: list[float] | None = None,
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
    element_id: str | None = None,
    figure_id: str | None = None,
    sub_bbox: list[float] | None = None,
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

