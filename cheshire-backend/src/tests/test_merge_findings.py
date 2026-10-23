import pytest
import json
from docling_core.types.doc import BoundingBox
from haystack.dataclasses import ChatMessage

from cheshire_configs.preprocessors.multistep.helpers import (
    LocalFinding,
    EvaluationChunk,
    ElementRef,
    FigureRef,
    ImageBoundingBox,
)
from cheshire_configs.preprocessors.multistep.tools import (
    add_local_finding,
    accept_local_finding,
    merge_findings,
)
from cheshire_configs.preprocessors.multistep.pipelines import (
    merge_findings_tool,
    build_dedup_pipeline,
)
from cheshire_configs.preprocessors.multistep.components.findings_parser import FindingsParser
from tools.helpers.output_schema import VulnerabilityDetails


DUMMY_IMAGE_BBOX = ImageBoundingBox(x1=0.0, y1=0.0, x2=10.0, y2=10.0)


# ===========================================================================
# 1. LocalFinding Schema & Validation Tests
# ===========================================================================

def test_local_finding_sub_bbox_coercion():
    # Flat single bbox should be coerced to list of bboxes
    lf1 = LocalFinding(
        element_id="elem_1",
        element_type="paragraph",
        finding="Vulnerability in text",
        standard_ref="Standard 1",
        severity="medium",
        confidence=0.8,
        sub_bbox=[100.0, 200.0, 300.0, 400.0],
    )
    assert lf1.sub_bbox == [[100.0, 200.0, 300.0, 400.0]]
    assert lf1.element_id == ["elem_1"]
    assert lf1.severity == "minor"
    assert lf1.confidence == 0.8

    # Multiple sub_bboxes should be preserved
    lf2 = LocalFinding(
        element_id=["elem_1", "elem_2"],
        element_type="diagram_node",
        finding="Incomplete diagram with multiple missing items",
        standard_ref="Standard 1",
        severity="high",
        confidence=0.9,
        sub_bbox=[[10.0, 20.0, 30.0, 40.0], [50.0, 60.0, 70.0, 80.0]],
    )
    assert lf2.sub_bbox == [[10.0, 20.0, 30.0, 40.0], [50.0, 60.0, 70.0, 80.0]]
    assert lf2.element_id == ["elem_1", "elem_2"]
    assert lf2.severity == "major"
    assert lf2.confidence == 0.9

    # None and empty
    lf3 = LocalFinding(
        element_type="paragraph",
        finding="Test",
        standard_ref="Standard",
        severity="low",
        confidence=1.0,
        sub_bbox=None,
        element_id=None,
    )
    assert lf3.sub_bbox is None
    assert lf3.element_id is None
    assert lf3.severity == "minor"
    assert lf3.confidence == 1.0

    # Stringified JSON
    lf4 = LocalFinding(
        element_id="['id_a', 'id_b']",
        element_type="paragraph",
        finding="Test",
        standard_ref="Standard",
        severity="observation",
        confidence=0.6,
        sub_bbox="[[1.0, 2.0, 3.0, 4.0]]",
    )
    assert lf4.sub_bbox == [[1.0, 2.0, 3.0, 4.0]]
    assert lf4.element_id == ["id_a", "id_b"]
    assert lf4.severity == "observation"
    assert lf4.confidence == 0.6


def test_local_finding_severity_and_confidence_rubric():
    # Severity 3-tier mapping
    assert LocalFinding(element_type="p", finding="f", standard_ref="s", severity="major", confidence=1.0).severity == "major"
    assert LocalFinding(element_type="p", finding="f", standard_ref="s", severity="critical", confidence=1.0).severity == "major"
    assert LocalFinding(element_type="p", finding="f", standard_ref="s", severity="high", confidence=1.0).severity == "major"
    assert LocalFinding(element_type="p", finding="f", standard_ref="s", severity="minor", confidence=0.8).severity == "minor"
    assert LocalFinding(element_type="p", finding="f", standard_ref="s", severity="medium", confidence=0.8).severity == "minor"
    assert LocalFinding(element_type="p", finding="f", standard_ref="s", severity="low", confidence=0.8).severity == "minor"
    assert LocalFinding(element_type="p", finding="f", standard_ref="s", severity="observation", confidence=0.6).severity == "observation"
    assert LocalFinding(element_type="p", finding="f", standard_ref="s", severity="advisory", confidence=0.6).severity == "observation"
    assert LocalFinding(element_type="p", finding="f", standard_ref="s", severity="unknown_value", confidence=0.6).severity == "observation"

    # Confidence clamping and defaulting
    assert LocalFinding(element_type="p", finding="f", standard_ref="s", severity="major", confidence=1.0).confidence == 1.0
    assert LocalFinding(element_type="p", finding="f", standard_ref="s", severity="major", confidence=0.8).confidence == 0.8
    assert LocalFinding(element_type="p", finding="f", standard_ref="s", severity="major", confidence=0.6).confidence == 0.6
    assert LocalFinding(element_type="p", finding="f", standard_ref="s", severity="major", confidence=1.5).confidence == 1.0
    assert LocalFinding(element_type="p", finding="f", standard_ref="s", severity="major", confidence=-0.5).confidence == 0.0


# ===========================================================================
# 2. merge_findings Function Tests
# ===========================================================================

def test_merge_findings_diagram_duplicates():
    # Finding A: TBD in diagram
    f1 = {
        "title": "Figure 1: TBD in node",
        "figure_id": "fig_arch",
        "element_id": "fig_arch_node_1",
        "sub_bbox": [100.0, 100.0, 200.0, 200.0],
        "element_type": "diagram_node",
        "finding": "Node contains placeholder 'TBD'",
        "standard_ref": "Architecture completeness standard",
        "severity": "minor",
        "confidence": 0.85,
        "recommendations": ["Replace TBD with concrete service name"],
        "web_references": ["https://standard.internal/arch"],
    }
    # Finding B: ??? in diagram
    f2 = {
        "title": "Figure 1: ??? in field",
        "figure_id": "fig_arch",
        "element_id": "fig_arch_node_2",
        "sub_bbox": [400.0, 400.0, 500.0, 500.0],
        "element_type": "diagram_node",
        "finding": "Field marked as '???' in diagram",
        "standard_ref": "Architecture completeness standard",
        "severity": "major",
        "confidence": 0.95,
        "recommendations": ["Clarify ??? component specifications"],
        "web_references": ["https://standard.internal/arch"],
    }

    result = merge_findings(
        findings=[f1, f2],
        title="Figure 1: Incomplete architecture diagram with placeholders",
        finding="Architecture diagram Figure 1 contains incomplete placeholders including TBD and ??? marks.",
    )

    merged: LocalFinding = result["finding"]
    assert isinstance(merged, LocalFinding)
    assert merged.title == "Figure 1: Incomplete architecture diagram with placeholders"
    assert merged.figure_id == "fig_arch"
    # Both sub_bboxes aggregated into list of lists
    assert merged.sub_bbox == [
        [100.0, 100.0, 200.0, 200.0],
        [400.0, 400.0, 500.0, 500.0],
    ]
    # Both element_ids aggregated
    assert merged.element_id == ["fig_arch_node_1", "fig_arch_node_2"]
    # Highest severity selected (major > minor)
    assert merged.severity == "major"
    # Max confidence selected (0.95 > 0.85)
    assert merged.confidence == 0.95
    # Unique recommendations & web references combined
    assert len(merged.recommendations) == 2
    assert len(merged.web_references) == 1


def test_merge_findings_text_paragraphs():
    f1 = LocalFinding(
        element_id="para_1",
        element_type="paragraph",
        title="Unencrypted transport in section 2.1",
        finding="HTTP protocol used for data transmission",
        standard_ref="Encryption standard",
        severity="minor",
        confidence=0.6,
        recommendations=["Use HTTPS"],
    )
    f2 = LocalFinding(
        element_id="para_2",
        element_type="paragraph",
        title="Unencrypted transport in section 2.2",
        finding="Plaintext socket connection described",
        standard_ref="Encryption standard",
        severity="major",
        confidence=0.8,
        recommendations=["Enforce TLS 1.3"],
    )

    result = merge_findings(
        findings=[f1, f2],
        title="Unencrypted communications across processing sections",
        finding="Unencrypted transport and plaintext connections detected.",
    )

    merged: LocalFinding = result["finding"]
    assert merged.element_id == ["para_1", "para_2"]
    assert merged.severity == "major"
    assert merged.confidence == 0.8
    assert "Use HTTPS" in merged.recommendations
    assert "Enforce TLS 1.3" in merged.recommendations


def test_merge_findings_tool_wrapper():
    tool = merge_findings_tool("accepted_findings")
    assert tool.name == "merge_findings"
    f1 = {
        "title": "Diag A",
        "figure_id": "fig_1",
        "sub_bbox": [10.0, 20.0, 30.0, 40.0],
        "element_type": "diagram_node",
        "finding": "Missing node",
        "standard_ref": "Standard",
        "severity": "medium",
        "confidence": 0.8,
    }
    f2 = {
        "title": "Diag B",
        "figure_id": "fig_1",
        "sub_bbox": [50.0, 60.0, 70.0, 80.0],
        "element_type": "diagram_node",
        "finding": "Missing edge",
        "standard_ref": "Standard",
        "severity": "high",
        "confidence": 0.9,
    }
    out = tool.invoke(
        findings=[f1, f2],
        title="Figure 1 Missing elements",
        finding="Diagram Figure 1 is missing both nodes and edges.",
    )
    assert "finding" in out
    merged: LocalFinding = out["finding"]
    assert len(merged.sub_bbox) == 2


# ===========================================================================
# 3. FindingsParser with Multiple Highlights
# ===========================================================================

def test_findings_parser_multiple_sub_bboxes():
    parser = FindingsParser()
    json_data = [
        {
            "title": "Multiple Diagram Incompleteness",
            "description": "TBD and ??? in diagram",
            "figure_id": "fig_1",
            "sub_bbox": [
                [0.1, 0.2, 0.3, 0.4],
                [0.5, 0.6, 0.7, 0.8],
            ]
        }
    ]
    message = ChatMessage.from_assistant(json.dumps(json_data))

    fig = FigureRef(
        figure_id="fig_1",
        page_number=2,
        bbox_image_px=[0.0, 0.0, 100.0, 100.0],
        bbox_pdf=BoundingBox(l=10.0, t=100.0, r=50.0, b=50.0),
        base64_png="dummy_base64",
    )
    chunk = EvaluationChunk(
        chunk_id="c0",
        heading="Sec",
        page_range=(1, 2),
        structured_text="text",
        figures=[fig],
    )

    result = parser.run(last_message=message, chunk=chunk)
    vulns = result["vulnerabilities"]
    assert len(vulns) == 1
    v: VulnerabilityDetails = vulns[0]
    assert v.page_no == 2
    # Multiple highlights mapped to bboxes
    assert len(v.bboxes) == 2
    # Primary bbox matches first bbox
    assert v.bbox == v.bboxes[0]
    assert v.bbox == BoundingBox(l=14.0, t=90.0, r=22.0, b=80.0)


# ===========================================================================
# 4. VulnerabilityDetails bboxes Synchronization
# ===========================================================================

def test_vulnerability_details_sync():
    b1 = BoundingBox(l=1.0, t=2.0, r=3.0, b=4.0)
    b2 = BoundingBox(l=5.0, t=6.0, r=7.0, b=8.0)

    # When created with bboxes only, primary bbox is synced to bboxes[0]
    v1 = VulnerabilityDetails(
        title="Test 1",
        description="Desc",
        page_no=1,
        bbox=None,  # type: ignore
        bboxes=[b1, b2],
        web_references=[],
        recommendations=[],
    )
    assert v1.bbox == b1
    assert len(v1.bboxes) == 2

    # When created with bbox only, bboxes is synced to [bbox]
    v2 = VulnerabilityDetails(
        title="Test 2",
        description="Desc",
        page_no=1,
        bbox=b1,
        web_references=[],
        recommendations=[],
    )
    assert v2.bboxes == [b1]


# ===========================================================================
# 5. Mandatory Recommendations Validation Tests
# ===========================================================================

def test_add_local_finding_mandatory_recommendations():
    # Calling add_local_finding with actionable recommendation succeeds
    res = add_local_finding(
        finding="Deprecated component",
        element_id="p_1",
        element_type="paragraph",
        recommendations=["Upgrade component to supported LTS version"],
    )
    assert res["finding"].recommendations == ["Upgrade component to supported LTS version"]

    # Calling add_local_finding without recommendations raises ValueError
    with pytest.raises(ValueError, match="Field 'recommendations' is mandatory"):
        add_local_finding(
            finding="Deprecated component",
            element_id="p_1",
            element_type="paragraph",
            recommendations=[],
        )

    # Calling with only whitespace recommendation raises ValueError
    with pytest.raises(ValueError, match="Field 'recommendations' is mandatory"):
        add_local_finding(
            finding="Deprecated component",
            element_id="p_1",
            element_type="paragraph",
            recommendations=["   "],
        )


def test_accept_local_finding_mandatory_recommendations():
    # Valid recommendations succeeds
    res = accept_local_finding(
        finding="Architecture gap",
        element_id="p_2",
        element_type="paragraph",
        recommendations=["Add detailed interface specifications"],
    )
    assert res["finding"].recommendations == ["Add detailed interface specifications"]

    # Missing recommendations raises ValueError
    with pytest.raises(ValueError, match="Field 'recommendations' is mandatory"):
        accept_local_finding(
            finding="Architecture gap",
            element_id="p_2",
            element_type="paragraph",
            recommendations=[],
        )
