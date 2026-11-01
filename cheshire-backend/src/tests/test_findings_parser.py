import pytest
import json
from haystack.dataclasses import ChatMessage
from docling_core.types.doc import BoundingBox

from cheshire_configs.preprocessors.multistep.components.findings_parser import FindingsParser
from cheshire_configs.preprocessors.multistep.helpers import (
    EvaluationChunk,
    ElementRef,
    FigureRef,
    ImageBoundingBox,
    TableCellRef,
)
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


def test_findings_parser_table_cell_snapping_subline_text():
    """
    Verify that an imprecise vision sub_bbox on a multi-line table cell snaps
    strictly to the column boundaries and the targeted bullet text line.
    """
    parser = FindingsParser()
    json_data = [
        {
            "title": "Operational & System Telemetry: Outdated GC pause specifications",
            "description": "Specifications reference JVM/Go GC pause times during large XML serialization cycles.",
            "figure_id": "table_crop_#/tables/0",
            # Imprecise sub_bbox shifted down and to the right into the next column
            "sub_bbox": [400.0, 500.0, 850.0, 750.0],
        }
    ]
    message = ChatMessage.from_assistant(json.dumps(json_data))

    desc_cell_bbox = BoundingBox(l=200.0, t=500.0, r=450.0, b=300.0)
    col3_cell_bbox = BoundingBox(l=450.0, t=500.0, r=550.0, b=300.0)

    table_cells = [
        TableCellRef(
            text="Operational & System Telemetry",
            bbox_pdf=BoundingBox(l=50.0, t=500.0, r=180.0, b=300.0),
            row_idx=1,
            col_idx=0,
        ),
        TableCellRef(
            text="E",
            bbox_pdf=BoundingBox(l=180.0, t=500.0, r=200.0, b=300.0),
            row_idx=1,
            col_idx=1,
        ),
        TableCellRef(
            text=(
                "Specifications:\n"
                "• JVM/Go GC pause times during large XML serialization cycles.\n"
                "• Streaming XML buffer memory allocation counters."
            ),
            bbox_pdf=desc_cell_bbox,
            row_idx=1,
            col_idx=2,
        ),
        TableCellRef(
            text="AWVTelemetry&PerformanceLogs_10-20-2026.xlsx",
            bbox_pdf=col3_cell_bbox,
            row_idx=1,
            col_idx=3,
        ),
    ]

    fig = FigureRef(
        figure_id="table_crop_#/tables/0",
        page_number=8,
        bbox_image_px=[0.0, 0.0, 1000.0, 400.0],
        bbox_pdf=BoundingBox(l=50.0, t=550.0, r=550.0, b=300.0),
        base64_png="dummy_base64",
        table_cells=table_cells,
    )
    chunk = create_test_chunk(figures=[fig])

    result = parser.run(last_message=message, chunk=chunk)
    vulns = result["vulnerabilities"]
    assert len(vulns) == 1
    v = vulns[0]

    # The snapped box must be strictly within the description column (l=200.0, r=450.0)
    # It must NOT bleed into the Excel icon column (r <= 450.0)
    assert v.bbox.l == 200.0
    assert v.bbox.r == 450.0
    # Vertically it must target segment 1 ("JVM/Go GC pause times")
    # cell_h = 200.0; segment 1 of 3 lines spans top_frac = 1/3 to bottom_frac = 2/3
    # t = 500 - (1/3)*200 = 433.333, b = 500 - (2/3)*200 = 366.667
    assert v.bbox.t < desc_cell_bbox.t  # below "Specifications:"
    assert v.bbox.b > desc_cell_bbox.b  # above "Streaming XML"


def test_findings_parser_table_element_id_cell_snapping():
    """
    Verify that findings anchored to element_id on a table snap to the matching cell.
    """
    parser = FindingsParser()
    json_data = [
        {
            "title": "Reports: Missing Attachment Format",
            "description": "Attachment AWVTransportLogs_10-25-2026.pdf is missing Class/Module field.",
            "element_id": "#/tables/0",
        }
    ]
    message = ChatMessage.from_assistant(json.dumps(json_data))

    target_cell_bbox = BoundingBox(l=450.0, t=500.0, r=550.0, b=300.0)
    table_cells = [
        TableCellRef(
            text="Internet & Perimeter Egress",
            bbox_pdf=BoundingBox(l=50.0, t=500.0, r=180.0, b=300.0),
            row_idx=1,
            col_idx=0,
        ),
        TableCellRef(
            text="AWVTransportLogs_10-25-2026.pdf",
            bbox_pdf=target_cell_bbox,
            row_idx=1,
            col_idx=3,
        ),
    ]

    elem = ElementRef(
        element_id="#/tables/0",
        label="table",
        page_number=8,
        bbox_image_px=DUMMY_IMAGE_BBOX,
        bbox_pdf=BoundingBox(l=50.0, t=550.0, r=550.0, b=300.0),
        text_excerpt="table content",
        table_cells=table_cells,
    )
    chunk = create_test_chunk(element_refs=[elem])

    result = parser.run(last_message=message, chunk=chunk)
    vulns = result["vulnerabilities"]
    assert len(vulns) == 1
    # Bbox snaps directly to the target cell
    assert vulns[0].bbox == target_cell_bbox


def test_findings_parser_table_title_priority_over_description():
    """
    Verify that table cell snapping prioritizes title subjects (e.g. RabbitMQ 3.12)
    over long narrative description text (e.g. Loan event streaming).
    """
    parser = FindingsParser()
    json_data = [
        {
            "title": "Message Queue: RabbitMQ 3.12 is out of community and commercial support",
            "description": "The Message Queue row specifies RabbitMQ 3.12 for loan event streaming. RabbitMQ 3.12 ended community support...",
            "element_id": "#/tables/1",
        }
    ]
    message = ChatMessage.from_assistant(json.dumps(json_data))

    mq_cell_bbox = BoundingBox(l=150.0, t=400.0, r=250.0, b=370.0)
    ver_cell_bbox = BoundingBox(l=260.0, t=400.0, r=320.0, b=370.0)
    desc_cell_bbox = BoundingBox(l=330.0, t=400.0, r=500.0, b=370.0)

    table_cells = [
        TableCellRef(text="Message Queue", bbox_pdf=BoundingBox(l=50.0, t=400.0, r=140.0, b=370.0), row_idx=5, col_idx=0),
        TableCellRef(text="RabbitMQ", bbox_pdf=mq_cell_bbox, row_idx=5, col_idx=1),
        TableCellRef(text="3.12", bbox_pdf=ver_cell_bbox, row_idx=5, col_idx=2),
        TableCellRef(text="Loan event streaming", bbox_pdf=desc_cell_bbox, row_idx=5, col_idx=3),
    ]

    elem = ElementRef(
        element_id="#/tables/1",
        label="table",
        page_number=5,
        bbox_image_px=DUMMY_IMAGE_BBOX,
        bbox_pdf=BoundingBox(l=50.0, t=600.0, r=500.0, b=200.0),
        text_excerpt="tech stack table",
        table_cells=table_cells,
    )
    chunk = create_test_chunk(element_refs=[elem])

    result = parser.run(last_message=message, chunk=chunk)
    vulns = result["vulnerabilities"]
    assert len(vulns) == 1
    # Bbox should cover the subject technology / version (stopping at r=320.0), NOT desc_cell_bbox (l=330.0)
    snapped_bbox = vulns[0].bbox
    assert snapped_bbox.r == 320.0
    assert snapped_bbox.r < desc_cell_bbox.l
    assert snapped_bbox.r == 320.0
    assert snapped_bbox.r < desc_cell_bbox.l or snapped_bbox.r != desc_cell_bbox.r


def test_findings_parser_table_multi_row_matching():
    """
    Verify that findings mentioning elements across multiple table rows
    produce highlights for all matched rows rather than collapsing to a single cell.
    """
    parser = FindingsParser()
    json_data = [
        {
            "title": "Reports: Missing Attachment Format for ReportA and ReportB",
            "description": "Both ReportA.pdf and ReportB.pdf lack specified output class formats in table.",
            "element_id": "#/tables/2",
        }
    ]
    message = ChatMessage.from_assistant(json.dumps(json_data))

    row1_cell = TableCellRef(text="ReportA.pdf", bbox_pdf=BoundingBox(l=50.0, t=500.0, r=200.0, b=450.0), row_idx=1, col_idx=0)
    row2_cell = TableCellRef(text="ReportB.pdf", bbox_pdf=BoundingBox(l=50.0, t=400.0, r=200.0, b=350.0), row_idx=2, col_idx=0)

    elem = ElementRef(
        element_id="#/tables/2",
        label="table",
        page_number=8,
        bbox_image_px=DUMMY_IMAGE_BBOX,
        bbox_pdf=BoundingBox(l=50.0, t=550.0, r=500.0, b=300.0),
        text_excerpt="reports table",
        table_cells=[row1_cell, row2_cell],
    )
    chunk = create_test_chunk(element_refs=[elem])

    result = parser.run(last_message=message, chunk=chunk)
    vulns = result["vulnerabilities"]
    assert len(vulns) == 1
    bboxes = vulns[0].bboxes
    # Both rows should be represented in bboxes
    assert len(bboxes) == 2
    y_tops = {b.t for b in bboxes}
    assert 500.0 in y_tops
    assert 400.0 in y_tops


def test_findings_parser_table_wide_finding_highlights_table():
    """
    Verify that findings regarding table-wide structure (e.g. 'lacks column headers')
    highlight the entire table bounding box rather than collapsing to a single cell.
    """
    parser = FindingsParser()
    json_data = [
        {
            "title": "Directories/Paths table lacks column headers in the statutory report block",
            "description": "The Directories/Paths table lacks column headers and uses hardcoded UNC paths.",
            "element_id": "#/tables/3",
        }
    ]
    message = ChatMessage.from_assistant(json.dumps(json_data))

    cell1 = TableCellRef(text=r"\\crestview-internal\Auditing_Section\AWV", bbox_pdf=BoundingBox(l=60.0, t=480.0, r=400.0, b=450.0), row_idx=0, col_idx=0)
    table_box = BoundingBox(l=50.0, t=500.0, r=500.0, b=200.0)

    elem = ElementRef(
        element_id="#/tables/3",
        label="table",
        page_number=13,
        bbox_image_px=DUMMY_IMAGE_BBOX,
        bbox_pdf=table_box,
        text_excerpt="directories table",
        table_cells=[cell1],
    )
    chunk = create_test_chunk(element_refs=[elem])

    result = parser.run(last_message=message, chunk=chunk)
    vulns = result["vulnerabilities"]
    assert len(vulns) == 1
    # Bbox must highlight the whole table, not just cell1
    assert vulns[0].bbox.l == table_box.l
    assert vulns[0].bbox.r == table_box.r
    assert vulns[0].bbox.t == table_box.t
    assert vulns[0].bbox.b == table_box.b


