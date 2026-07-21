import pytest
import json
from haystack.dataclasses import ChatMessage
from docling_core.types.doc import BoundingBox

from cheshire_configs.preprocessors.multistep.components.findings_parser import FindingsParser
from cheshire_configs.preprocessors.multistep.helpers import EvaluationChunk, ElementRef, FigureRef, ImageBoundingBox
from tools.helpers.output_schema import VulnerabilityDetails

# A dummy ImageBoundingBox for ElementRef initialization
DUMMY_IMAGE_BBOX = ImageBoundingBox(x1=0.0, y1=0.0, x2=10.0, y2=10.0)

def create_test_chunk(element_refs=None, figures=None) -> EvaluationChunk:
    """Helper to create a basic EvaluationChunk for testing."""
    return EvaluationChunk(
        chunk_id="chunk_0",
        heading="Test Section",
        page_range=(1, 2),
        structured_text="dummy text",
        element_refs=element_refs or [],
        figures=figures or []
    )

def test_findings_parser_valid_json_list():
    parser = FindingsParser()
    json_data = [
        {
            "title": "SQL Injection",
            "description": "SQL injection vulnerability in endpoint",
            "page_no": 1,
            "element_id": "elem_1",
            "web_references": ["https://owasp.org"],
            "recommendations": ["Use parameterized queries"]
        }
    ]
    message = ChatMessage.from_assistant(json.dumps(json_data))
    
    elem = ElementRef(
        element_id="elem_1",
        label="paragraph",
        page_number=1,
        bbox_image_px=DUMMY_IMAGE_BBOX,
        bbox_pdf=BoundingBox(l=10.0, t=100.0, r=50.0, b=50.0),
        text_excerpt="This is element 1 content"
    )
    chunk = create_test_chunk(element_refs=[elem])
    
    result = parser.run(last_message=message, chunk=chunk)
    vulns = result["vulnerabilities"]
    
    assert len(vulns) == 1
    v = vulns[0]
    assert isinstance(v, VulnerabilityDetails)
    assert v.title == "SQL Injection"
    assert v.description == "SQL injection vulnerability in endpoint"
    assert v.page_no == 1
    assert v.bbox == BoundingBox(l=10.0, t=100.0, r=50.0, b=50.0)
    assert v.web_references == ["https://owasp.org"]
    assert v.recommendations == ["Use parameterized queries"]

def test_findings_parser_valid_json_dict():
    parser = FindingsParser()
    json_data = {
        "title": "XSS Vulnerability",
        "description": "Cross-site scripting in comment section",
        "page_no": 2,
        "element_id": "elem_2"
    }
    message = ChatMessage.from_assistant(json.dumps(json_data))
    
    elem = ElementRef(
        element_id="elem_2",
        label="paragraph",
        page_number=2,
        bbox_image_px=DUMMY_IMAGE_BBOX,
        bbox_pdf=BoundingBox(l=5.0, t=20.0, r=25.0, b=10.0),
        text_excerpt="This is element 2 content"
    )
    chunk = create_test_chunk(element_refs=[elem])
    
    result = parser.run(last_message=message, chunk=chunk)
    vulns = result["vulnerabilities"]
    
    assert len(vulns) == 1
    v = vulns[0]
    assert v.title == "XSS Vulnerability"
    assert v.bbox == BoundingBox(l=5.0, t=20.0, r=25.0, b=10.0)

def test_findings_parser_markdown_code_block():
    parser = FindingsParser()
    json_str = """
```json
[
  {
    "title": "Vuln 1",
    "description": "Description 1",
    "page_no": 1
  }
]
```
"""
    message = ChatMessage.from_assistant(json_str)
    chunk = create_test_chunk()
    
    result = parser.run(last_message=message, chunk=chunk)
    vulns = result["vulnerabilities"]
    assert len(vulns) == 1
    assert vulns[0].title == "Vuln 1"

def test_findings_parser_invalid_json():
    parser = FindingsParser()
    message = ChatMessage.from_assistant('{"title": "Broken JSON"')
    chunk = create_test_chunk()
    
    result = parser.run(last_message=message, chunk=chunk)
    assert result == {"vulnerabilities": []}

def test_findings_parser_unexpected_json_types():
    parser = FindingsParser()
    chunk = create_test_chunk()
    
    # 1. String output
    msg_str = ChatMessage.from_assistant('"No vulnerabilities found."')
    assert parser.run(last_message=msg_str, chunk=chunk) == {"vulnerabilities": []}
    
    # 2. Integer output
    msg_int = ChatMessage.from_assistant("12345")
    assert parser.run(last_message=msg_int, chunk=chunk) == {"vulnerabilities": []}
    
    # 3. List of non-dict items mixed with a dict
    json_data = ["invalid_finding", {"title": "Valid Vuln", "description": "Valid Desc"}]
    msg_mixed = ChatMessage.from_assistant(json.dumps(json_data))
    result = parser.run(last_message=msg_mixed, chunk=chunk)
    vulns = result["vulnerabilities"]
    assert len(vulns) == 1
    assert vulns[0].title == "Valid Vuln"

def test_findings_parser_missing_required_fields():
    parser = FindingsParser()
    # Pydantic's VulnerabilityDetails requires both 'title' and 'description'
    json_data = [
        {"title": "Title Only"},
        {"description": "Description Only"},
        {"title": "Full", "description": "Details here"}
    ]
    message = ChatMessage.from_assistant(json.dumps(json_data))
    chunk = create_test_chunk()
    
    result = parser.run(last_message=message, chunk=chunk)
    vulns = result["vulnerabilities"]
    
    assert len(vulns) == 1
    assert vulns[0].title == "Full"

def test_findings_parser_figure_resolution_normalized():
    parser = FindingsParser()
    # Coordinates in normalized [0.0, 1.0] range
    json_data = [
        {
            "title": "Fig Vuln",
            "description": "Vuln in diagram",
            "figure_id": "fig_1",
            "sub_bbox": [0.1, 0.2, 0.3, 0.4]
        }
    ]
    message = ChatMessage.from_assistant(json.dumps(json_data))
    
    fig = FigureRef(
        figure_id="fig_1",
        page_number=3,
        bbox_image_px=[0.0, 0.0, 100.0, 100.0],
        bbox_pdf=BoundingBox(l=10.0, t=100.0, r=50.0, b=50.0),
        base64_png="dummy_base64"
    )
    chunk = create_test_chunk(figures=[fig])
    
    result = parser.run(last_message=message, chunk=chunk)
    vulns = result["vulnerabilities"]
    
    assert len(vulns) == 1
    v = vulns[0]
    # fig_width = 50 - 10 = 40
    # fig_height = 100 - 50 = 50
    # l = 10 + 0.1 * 40 = 14
    # t = 100 - 0.2 * 50 = 90
    # r = 10 + 0.3 * 40 = 22
    # b = 100 - 0.4 * 50 = 80
    assert v.page_no == 3
    assert v.bbox == BoundingBox(l=14.0, t=90.0, r=22.0, b=80.0)

def test_findings_parser_figure_resolution_scaled():
    parser = FindingsParser()
    # Coordinates in 0-1000 range (max_coord = 400.0 > 1.0, scale_factor = 1000.0)
    json_data = [
        {
            "title": "Fig Vuln Scaled",
            "description": "Vuln in diagram scaled",
            "figure_id": "fig_1",
            "sub_bbox": [100.0, 200.0, 300.0, 400.0]
        }
    ]
    message = ChatMessage.from_assistant(json.dumps(json_data))
    
    fig = FigureRef(
        figure_id="fig_1",
        page_number=3,
        bbox_image_px=[0.0, 0.0, 100.0, 100.0],
        bbox_pdf=BoundingBox(l=10.0, t=100.0, r=50.0, b=50.0),
        base64_png="dummy_base64"
    )
    chunk = create_test_chunk(figures=[fig])
    
    result = parser.run(last_message=message, chunk=chunk)
    vulns = result["vulnerabilities"]
    
    assert len(vulns) == 1
    v = vulns[0]
    # Should result in identical bbox as normalized [0.1, 0.2, 0.3, 0.4]
    assert v.bbox == BoundingBox(l=14.0, t=90.0, r=22.0, b=80.0)

def test_findings_parser_figure_resolution_clamping():
    parser = FindingsParser()
    # Coordinates that require clamping: negative and exceeds scale_factor bounds
    json_data = [
        {
            "title": "Fig Vuln Clamp",
            "description": "Out of bounds coords",
            "figure_id": "fig_1",
            "sub_bbox": [-50.0, 1500.0, 50.0, 100.0]
        }
    ]
    message = ChatMessage.from_assistant(json.dumps(json_data))
    
    fig = FigureRef(
        figure_id="fig_1",
        page_number=3,
        bbox_image_px=[0.0, 0.0, 100.0, 100.0],
        bbox_pdf=BoundingBox(l=10.0, t=100.0, r=50.0, b=50.0),
        base64_png="dummy_base64"
    )
    chunk = create_test_chunk(figures=[fig])
    
    result = parser.run(last_message=message, chunk=chunk)
    vulns = result["vulnerabilities"]
    
    assert len(vulns) == 1
    v = vulns[0]
    # max_coord = 1500.0 > 1.0, scale_factor = 1000.0
    # scaled_x1 = -50.0 -> normalized = -0.05 -> clamped to 0.0
    # scaled_y1 = 1500.0 -> normalized = 1.5 -> clamped to 1.0
    # scaled_x2 = 50.0 -> normalized = 0.05 -> clamped to 0.05
    # scaled_y2 = 100.0 -> normalized = 0.1 -> clamped to 0.1
    # l = 10.0 + 0.0 * 40.0 = 10.0
    # t = 100.0 - 1.0 * 50.0 = 50.0
    # r = 10.0 + 0.05 * 40.0 = 12.0
    # b = 100.0 - 0.1 * 50.0 = 95.0
    assert v.bbox == BoundingBox(l=10.0, t=50.0, r=12.0, b=95.0)

def test_findings_parser_figure_fallback_bbox():
    parser = FindingsParser()
    fig = FigureRef(
        figure_id="fig_1",
        page_number=3,
        bbox_image_px=[0.0, 0.0, 100.0, 100.0],
        bbox_pdf=BoundingBox(l=10.0, t=100.0, r=50.0, b=50.0),
        base64_png="dummy_base64"
    )
    chunk = create_test_chunk(figures=[fig])
    
    # Test cases for invalid sub_bbox shapes/types falling back to figure's bbox_pdf
    cases = [
        None,                        # None
        [0.1, 0.2],                  # Length too short
        [0.1, 0.2, 0.3, 0.4, 0.5],   # Length too long
        "not a list"                 # Wrong type
    ]
    
    for sub_bbox in cases:
        json_data = [
            {
                "title": "Fallback Test",
                "description": "Invalid sub_bbox",
                "figure_id": "fig_1",
                "sub_bbox": sub_bbox
            }
        ]
        message = ChatMessage.from_assistant(json.dumps(json_data))
        result = parser.run(last_message=message, chunk=chunk)
        vulns = result["vulnerabilities"]
        
        assert len(vulns) == 1
        assert vulns[0].bbox == BoundingBox(l=10.0, t=100.0, r=50.0, b=50.0)

def test_findings_parser_unresolvable_ids():
    parser = FindingsParser()
    # element_id or figure_id not present in chunk
    json_data = [
        {
            "title": "Unresolvable Element",
            "description": "No elem in chunk matching this ID",
            "element_id": "missing_elem"
        },
        {
            "title": "Unresolvable Figure",
            "description": "No figure in chunk matching this ID",
            "figure_id": "missing_fig"
        }
    ]
    message = ChatMessage.from_assistant(json.dumps(json_data))
    chunk = create_test_chunk()
    
    result = parser.run(last_message=message, chunk=chunk)
    vulns = result["vulnerabilities"]
    
    assert len(vulns) == 2
    # Unresolved elements/figures still output, but with a default bounding box of 0s
    assert vulns[0].bbox == BoundingBox(l=0, t=0, r=0, b=0)
    assert vulns[1].bbox == BoundingBox(l=0, t=0, r=0, b=0)

def test_findings_parser_none_message_text():
    parser = FindingsParser()
    message = ChatMessage.from_assistant(None)
    chunk = create_test_chunk()
    
    result = parser.run(last_message=message, chunk=chunk)
    assert result == {"vulnerabilities": []}
