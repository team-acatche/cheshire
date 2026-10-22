from docling_core.types.doc import BoundingBox, CoordOrigin
from docling_core.types.doc.document import DoclingDocument
from cheshire_configs.preprocessors.multistep.helpers import (
    DEFAULT_COL_WIDTH_PX,
    DEFAULT_ROW_HEIGHT_PX,
    _detect_compound_header_split,
    _format_table_markdown,
    _sanitize_table_cell_text,
    _table_has_empty_cells,
    _table_needs_visual_crop,
    build_document_index,
)


class MockCell:
    def __init__(self, text: str, column_header: bool = False):
        self.text = text
        self.column_header = column_header


class MockProv:
    def __init__(self, bbox: BoundingBox, page_no: int = 1):
        self.bbox = bbox
        self.page_no = page_no


class MockPicture:
    def __init__(self, bbox: BoundingBox, page_no: int = 1):
        self.prov = [MockProv(bbox, page_no)]


class MockTableData:
    def __init__(self, grid, row_bboxes=None, col_bboxes=None):
        self.grid = grid
        self._row_bboxes = row_bboxes or {}
        self._col_bboxes = col_bboxes or {}

    def get_row_bounding_boxes(self):
        return self._row_bboxes

    def get_column_bounding_boxes(self):
        return self._col_bboxes


class MockTableItem:
    def __init__(self, grid, bbox: BoundingBox, page_no: int = 1, self_ref: str = "#/tables/0", row_bboxes=None, col_bboxes=None):
        self.data = MockTableData(grid, row_bboxes, col_bboxes)
        self.prov = [MockProv(bbox, page_no)]
        self.self_ref = self_ref


def test_detect_compound_header_split_with_layout_bias():
    """Verify that multi-word compound headers with independent keywords and picture bias split cleanly."""
    res = _detect_compound_header_split(
        "File Type Link",
        col_width=240.0,
        has_left_biased_picture=True,
    )
    assert res == ("File Type", "Link")

    res_format = _detect_compound_header_split(
        "Attachment Format",
        col_width=200.0,
        has_left_biased_picture=True,
    )
    assert res_format == ("Attachment", "Format")


def test_detect_compound_header_split_explicit_delimiters():
    """Verify that newlines and multi-space delimiters trigger compound splitting."""
    res_nl = _detect_compound_header_split("File Type\nLink", col_width=180.0)
    assert res_nl == ("File Type", "Link")

    res_space = _detect_compound_header_split("File Type   Link", col_width=180.0)
    assert res_space == ("File Type", "Link")


def test_detect_compound_header_split_no_split():
    """Verify that legitimate single column titles are not erroneously split."""
    assert _detect_compound_header_split("File Name", col_width=150.0) is None
    assert _detect_compound_header_split("Class / Module", col_width=150.0) is None
    assert _detect_compound_header_split("GitLab Link/s", col_width=150.0, has_left_biased_picture=False) is None


def test_format_table_markdown_compound_column_expansion():
    """Verify that under-segmented compound header columns expand and align empty cells properly."""
    grid = [
        [MockCell("File Type Link", column_header=True), MockCell("Description", column_header=True)],
        [MockCell("", column_header=False), MockCell("Business Requirements Document", column_header=False)],
    ]
    table_bbox = BoundingBox(l=50.0, t=100.0, r=550.0, b=200.0, coord_origin=CoordOrigin.TOPLEFT)
    row_bboxes = {
        0: BoundingBox(l=50.0, t=100.0, r=550.0, b=130.0, coord_origin=CoordOrigin.TOPLEFT),
        1: BoundingBox(l=50.0, t=130.0, r=550.0, b=200.0, coord_origin=CoordOrigin.TOPLEFT),
    }
    col_bboxes = {
        0: BoundingBox(l=50.0, t=100.0, r=370.0, b=200.0, coord_origin=CoordOrigin.TOPLEFT),
        1: BoundingBox(l=370.0, t=100.0, r=550.0, b=200.0, coord_origin=CoordOrigin.TOPLEFT),
    }
    table_item = MockTableItem(grid, table_bbox, page_no=1, row_bboxes=row_bboxes, col_bboxes=col_bboxes)

    # Document with a picture in the left half of column 0
    doc = DoclingDocument(name="test_table_doc")
    doc.pages[1] = type('MockPage', (), {'size': type('MockSize', (), {'height': 792.0, 'width': 612.0})()})()
    pic_bbox = BoundingBox(l=70.0, t=140.0, r=100.0, b=170.0, coord_origin=CoordOrigin.TOPLEFT)
    doc.pictures.append(MockPicture(pic_bbox, page_no=1))

    md, _ = _format_table_markdown(table_item, doc, last_header=None, is_continuation=False)

    lines = [line.strip() for line in md.strip().split("\n") if line.strip()]
    header_line = lines[0]
    data_line = lines[2]

    # Verify header row was expanded to 3 columns
    assert "File Type" in header_line
    assert "Link" in header_line
    assert "Description" in header_line

    # Verify data row aligned the icon under File Type and left Link empty
    cells = [c.strip() for c in data_line.split("|")[1:-1]]
    assert len(cells) == 3
    assert cells[0] == "[Embedded Icon]"
    assert cells[1] == ""
    assert cells[2] == "Business Requirements Document"

    # Verify empty cell detection fires for the newly created empty Link cell
    assert _table_has_empty_cells(md) is True


class MockItem:
    def __init__(self, label: str, text: str = "", self_ref: str = "", page_no: int = 1, grid=None):
        self.label = label
        self.text = text
        self.self_ref = self_ref
        self.prov = [MockProv(BoundingBox(l=0, t=0, r=10, b=10), page_no=page_no)]
        if grid is not None:
            self.data = MockTableData(grid)


class MockDoc:
    def __init__(self, items):
        self.items = items
        self.pages = {1: type('MockPage', (), {'size': type('MockSize', (), {'height': 792.0, 'width': 612.0})()})()}
        self.pictures = []

    def iterate_items(self):
        for item in self.items:
            yield item, 0


def test_build_document_index_reference_documents_extraction():
    """Verify that build_document_index extracts reference document titles and codes from tables and overview text."""
    items = [
        MockItem(label="section_header", text="1. Overview", self_ref="#/texts/1", page_no=1),
        MockItem(
            label="paragraph",
            text="This platform was designed in accordance with the System Requirements Specification (SRS-2025-LO-004).",
            self_ref="#/texts/2",
            page_no=1,
        ),
        MockItem(label="section_header", text="B. Reference Documents", self_ref="#/texts/3", page_no=4),
        MockItem(
            label="table",
            self_ref="#/tables/5",
            page_no=4,
            grid=[
                [MockCell("Document Title", column_header=True), MockCell("Document Reference / Link", column_header=True)],
                [MockCell("System Requirements Specification - SentroLoan"), MockCell("SRS-2025-LO-004")],
                [MockCell("Enterprise Architecture Standards v4.2"), MockCell("EAS-2024-SEC-011")],
                [MockCell("Security & Compliance Checklist"), MockCell("SEC-CHK-2025-Q1")],
            ],
        ),
        # Attachments table under same section should be excluded from reference_documents
        MockItem(
            label="table",
            self_ref="#/tables/6",
            page_no=4,
            grid=[
                [MockCell("File Name", column_header=True), MockCell("Format", column_header=True), MockCell("Description", column_header=True)],
                [MockCell("LoanApplication.docx"), MockCell("Word"), MockCell("Template document")],
            ],
        ),
    ]
    doc = MockDoc(items)

    index = build_document_index(doc)

    assert "reference_documents" in index
    ref_docs = index["reference_documents"]

    # Table entries extracted with title + reference code
    assert "System Requirements Specification - SentroLoan (SRS-2025-LO-004)" in ref_docs
    assert "Enterprise Architecture Standards v4.2 (EAS-2024-SEC-011)" in ref_docs
    assert "Security & Compliance Checklist (SEC-CHK-2025-Q1)" in ref_docs

    # Attachment table entries not erroneously included
    assert not any("LoanApplication.docx" in d for d in ref_docs)


def test_sanitize_table_cell_text_removes_soft_hyphens_and_artifacts():
    """Verify that soft hyphens, zero-width characters, and non-printing artifacts are removed."""
    dirty = "LOA\ufffeSCR-013: Manual\xadApproval\u200b and Verification\ufeff\x02"
    cleaned = _sanitize_table_cell_text(dirty)
    assert cleaned == "LOASCR-013: ManualApproval and Verification"


def test_sanitize_table_cell_text_normalizes_hyphen_linebreaks():
    """Verify that hyphen-split words across linebreaks are rejoined."""
    split_text = "LOA-SCR-\n 013: Manual Approval\n/ Decline Screen"
    cleaned = _sanitize_table_cell_text(split_text)
    assert "LOA-SCR-013: Manual Approval / Decline Screen" in cleaned


def test_table_needs_visual_crop_empty_cells():
    """Verify that a table with empty data cells triggers a visual crop."""
    md_with_empty = "| Col1 | Col2 |\n|---|---|\n| Value |  |\n"
    grid = [[MockCell("Col1", True), MockCell("Col2", True)], [MockCell("Value"), MockCell("")]]
    bbox = BoundingBox(l=50.0, t=100.0, r=400.0, b=200.0, coord_origin=CoordOrigin.TOPLEFT)
    item = MockTableItem(grid, bbox)
    assert _table_needs_visual_crop(item, md_with_empty, page_h=792.0) is True


def test_table_needs_visual_crop_geometric_clipping():
    """Verify that a table with horizontally clipped cell bounding boxes triggers a visual crop."""
    md_complete = "| Module Specifications |\n|---|\n| Line 1 |\n| Line 2 |\n"
    grid = [[MockCell("Module Specifications", True)], [MockCell("Line 1")], [MockCell("Line 2")]]
    table_bbox = BoundingBox(l=50.0, t=100.0, r=550.0, b=250.0, coord_origin=CoordOrigin.TOPLEFT)
    col_bboxes = {0: BoundingBox(l=50.0, t=100.0, r=320.0, b=250.0, coord_origin=CoordOrigin.TOPLEFT)}
    item = MockTableItem(grid, table_bbox, col_bboxes=col_bboxes)

    assert _table_needs_visual_crop(item, md_complete, page_h=792.0) is True


def test_table_needs_visual_crop_single_col_anomaly():
    """Verify that a multi-row table collapsed into 1 column on wide aspect ratio triggers a visual crop."""
    md = "| Header |\n|---|\n| Row 1 |\n| Row 2 |\n| Row 3 |\n"
    grid = [[MockCell("Header", True)], [MockCell("Row 1")], [MockCell("Row 2")], [MockCell("Row 3")]]
    table_bbox = BoundingBox(l=50.0, t=100.0, r=500.0, b=220.0, coord_origin=CoordOrigin.TOPLEFT)
    col_bboxes = {0: BoundingBox(l=50.0, t=100.0, r=490.0, b=220.0, coord_origin=CoordOrigin.TOPLEFT)}
    item = MockTableItem(grid, table_bbox, col_bboxes=col_bboxes)

    assert _table_needs_visual_crop(item, md, page_h=792.0) is True


def test_table_needs_visual_crop_normal_table():
    """Verify that a properly extracted, full-coverage table with multiple columns does not trigger visual crop."""
    md = "| Col1 | Col2 |\n|---|---|\n| A | B |\n| C | D |\n"
    grid = [[MockCell("Col1", True), MockCell("Col2", True)], [MockCell("A"), MockCell("B")], [MockCell("C"), MockCell("D")]]
    table_bbox = BoundingBox(l=50.0, t=100.0, r=550.0, b=200.0, coord_origin=CoordOrigin.TOPLEFT)
    col_bboxes = {
        0: BoundingBox(l=50.0, t=100.0, r=300.0, b=200.0, coord_origin=CoordOrigin.TOPLEFT),
        1: BoundingBox(l=300.0, t=100.0, r=540.0, b=200.0, coord_origin=CoordOrigin.TOPLEFT),
    }
    item = MockTableItem(grid, table_bbox, col_bboxes=col_bboxes)

    assert _table_needs_visual_crop(item, md, page_h=792.0) is False

