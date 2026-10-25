from docling_core.types.doc import BoundingBox, CoordOrigin
from docling_core.types.doc.document import DoclingDocument
from cheshire_configs.preprocessors.multistep.helpers import (
    DEFAULT_COL_WIDTH_PX,
    DEFAULT_ROW_HEIGHT_PX,
    FOOTER_MAX_TOP_RATIO,
    _detect_compound_header_split,
    _detect_document_footer_top,
    _format_cell_with_icons,
    _format_table_markdown,
    _infer_cell_value_type,
    _is_category_divider_row,
    _is_footer_element,
    _is_table_footer_row,
    _sanitize_table_cell_text,
    _table_has_empty_cells,
    _table_needs_visual_crop,
    build_document_index,
    is_horizontal_two_column_table,
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


def test_is_table_footer_row_detection():
    """Verify that a trailing table row matching footer metadata in the footer zone is identified."""
    footer_row = [MockCell("Classification: AsianBank Confidential"), MockCell("Document Owner: ITSD")]
    cell_bounds = {
        (2, 0): {"l": 50.0, "r": 250.0, "t": 720.0, "b": 740.0},
        (2, 1): {"l": 250.0, "r": 500.0, "t": 720.0, "b": 740.0},
    }
    assert _is_table_footer_row(footer_row, r_idx=2, cell_bounds=cell_bounds, page_h=792.0) is True

    # Normal row in footer zone should NOT be flagged as footer
    normal_row = [MockCell("Module A"), MockCell("Active status")]
    assert _is_table_footer_row(normal_row, r_idx=2, cell_bounds=cell_bounds, page_h=792.0) is False

    # Footer text located high on page (not in footer band) should NOT be flagged as footer
    high_bounds = {
        (0, 0): {"l": 50.0, "r": 250.0, "t": 100.0, "b": 120.0},
        (0, 1): {"l": 250.0, "r": 500.0, "t": 100.0, "b": 120.0},
    }
    assert _is_table_footer_row(footer_row, r_idx=0, cell_bounds=high_bounds, page_h=792.0) is False


def test_format_table_markdown_prunes_absorbed_footer_rows():
    """Verify that _format_table_markdown strips swallowed footer rows from the table output."""
    grid = [
        [MockCell("Description of Change", True), MockCell("Revised By", True), MockCell("Version", True)],
        [MockCell("Initial draft"), MockCell("J. Mendoza"), MockCell("1.0")],
        [MockCell("Classification: AsianBank Confidential"), MockCell("Document Owner: ITSD"), MockCell("Page 2 of 15")],
    ]
    table_bbox = BoundingBox(l=50.0, t=600.0, r=550.0, b=750.0, coord_origin=CoordOrigin.TOPLEFT)
    col_bboxes = {
        0: BoundingBox(l=50.0, t=600.0, r=250.0, b=750.0, coord_origin=CoordOrigin.TOPLEFT),
        1: BoundingBox(l=250.0, t=600.0, r=400.0, b=750.0, coord_origin=CoordOrigin.TOPLEFT),
        2: BoundingBox(l=400.0, t=600.0, r=550.0, b=750.0, coord_origin=CoordOrigin.TOPLEFT),
    }
    item = MockTableItem(grid, table_bbox, col_bboxes=col_bboxes)
    # Set cell bounds on bottom row into the footer zone
    doc = MockDoc([])
    doc.pages[1] = type("MockPage", (), {"size": type("MockSize", (), {"height": 792.0})()})()

    md, _ = _format_table_markdown(item, doc, last_header=None, is_continuation=False)

    # Output table must retain genuine row and prune footer row
    assert "Initial draft" in md
    assert "J. Mendoza" in md
    assert "Classification: AsianBank Confidential" not in md
    assert "Document Owner: ITSD" not in md


def test_is_footer_element_detection():
    """Verify that standalone items in the bottom margin matching footer metadata are identified."""
    class MockElementItem:
        def __init__(self, text: str, bbox: BoundingBox):
            self.text = text
            self.prov = [MockProv(bbox, page_no=1)]

    footer_bbox = BoundingBox(l=50.0, t=730.0, r=550.0, b=750.0, coord_origin=CoordOrigin.TOPLEFT)
    footer_item = MockElementItem("Classification: AsianBank Confidential | Page No.: 2 of 15", footer_bbox)
    doc = MockDoc([])

    # In footer zone with footer metadata
    assert _is_footer_element(footer_item, doc, page_h=792.0) is True

    # In footer zone but without footer metadata
    body_item = MockElementItem("Standard architecture description text.", footer_bbox)
    assert _is_footer_element(body_item, doc, page_h=792.0) is False

    # In middle of page with footer metadata
    high_bbox = BoundingBox(l=50.0, t=200.0, r=550.0, b=220.0, coord_origin=CoordOrigin.TOPLEFT)
    high_item = MockElementItem("Classification: AsianBank Confidential", high_bbox)
    assert _is_footer_element(high_item, doc, page_h=792.0) is False


def test_detect_document_footer_top_tall_footer():
    """Verify that _detect_document_footer_top adapts dynamically to tall footer (>20% of page)."""
    class MockElementItem:
        def __init__(self, text: str, bbox: BoundingBox, label: str = "text"):
            self.text = text
            self.label = label
            self.prov = [MockProv(bbox, page_no=1)]

    # A tall 3-line legal disclaimer footer starting at y=580 on page_h=792 (starts at ~73% of page)
    tall_footer_bbox = BoundingBox(l=50.0, t=580.0, r=550.0, b=760.0, coord_origin=CoordOrigin.TOPLEFT)
    footer_text = MockElementItem("Classification: Strictly Confidential\nAll rights reserved", tall_footer_bbox)
    doc = MockDoc([])
    doc.texts = [footer_text]
    doc.pages[1] = type("MockPage", (), {"size": type("MockSize", (), {"height": 792.0})()})()

    footer_top = _detect_document_footer_top(doc, page_h=792.0)
    # Headroom gives 580 - 10 = 570
    assert footer_top == 570.0


def test_detect_document_footer_top_compact_footer():
    """Verify that _detect_document_footer_top adapts dynamically to compact footer (<10% of page)."""
    class MockElementItem:
        def __init__(self, text: str, bbox: BoundingBox, label: str = "page_footer"):
            self.text = text
            self.label = label
            self.prov = [MockProv(bbox, page_no=1)]

    # A single compact 1-line footer at bottom (y=750 on page_h=792, ~95% of page)
    compact_footer_bbox = BoundingBox(l=50.0, t=750.0, r=550.0, b=770.0, coord_origin=CoordOrigin.TOPLEFT)
    footer_item = MockElementItem("Page 1 of 10", compact_footer_bbox, label="page_footer")
    doc = MockDoc([])
    doc.texts = [footer_item]
    doc.pages[1] = type("MockPage", (), {"size": type("MockSize", (), {"height": 792.0})()})()

    footer_top = _detect_document_footer_top(doc, page_h=792.0)
    # Headroom gives 750 - 10 = 740
    assert footer_top == 740.0


def test_is_table_footer_row_tall_footer_dynamic():
    """Verify that _is_table_footer_row prunes tall footers when passed dynamic footer_top."""
    tall_footer_row = [MockCell("Classification: Strictly Confidential"), MockCell("Doc Title: Specs")]
    # Located at y=600 (which is above static 0.85 * 792 = 673, but below dynamic footer_top 570)
    cell_bounds = {
        (5, 0): {"l": 50.0, "r": 250.0, "t": 600.0, "b": 630.0},
        (5, 1): {"l": 250.0, "r": 500.0, "t": 600.0, "b": 630.0},
    }
    # With default static threshold (0.65 fallback), y=600 is below 0.65 * 792 = 514.8, so it would not trigger if threshold were 673.
    # With explicit dynamic footer_top = 570, y=600 >= 570 -> identified as footer!
    assert _is_table_footer_row(tall_footer_row, r_idx=5, cell_bounds=cell_bounds, page_h=792.0, footer_top=570.0) is True

    # normal row at y=600 should not be flagged as footer
    normal_row = [MockCell("Specification Step 5"), MockCell("Active")]
    assert _is_table_footer_row(normal_row, r_idx=5, cell_bounds=cell_bounds, page_h=792.0, footer_top=570.0) is False


def test_detect_compound_header_split_slash_guard():
    """verify that slashes like activities / manhours do not split without layout picture bias."""
    # without picture bias, activities / manhours should remain a single column header
    assert _detect_compound_header_split(
        "ACTIVITIES / MANHOURS",
        col_width=250.0,
        has_left_biased_picture=False,
        has_right_biased_picture=False,
    ) is None

    # with picture bias, slash split should trigger
    assert _detect_compound_header_split(
        "ACTIVITIES / MANHOURS",
        col_width=250.0,
        has_left_biased_picture=True,
    ) == ("ACTIVITIES", "MANHOURS")

    # explicit pipe delimiter splits regardless of picture bias
    assert _detect_compound_header_split(
        "ACTIVITIES | MANHOURS",
        col_width=250.0,
        has_left_biased_picture=False,
    ) == ("ACTIVITIES", "MANHOURS")


def test_is_horizontal_two_column_table_detection():
    """verify that horizontal property tables are distinguished from vertical two-column tables."""
    # horizontal key-value table with colons
    horizontal_grid = [
        [MockCell("Application:"), MockCell("FinCEN Rule 17-B Serialization and Reporting Service")],
        [MockCell("Framework:"), MockCell(".NET 10.0")],
        [MockCell("Database:"), MockCell("SQL Server 2022")],
    ]
    assert is_horizontal_two_column_table(horizontal_grid) is True

    # horizontal key-value table without colons but with known property keys
    prop_grid = [
        [MockCell("Application"), MockCell("FinCEN Rule 17-B Serialization and Reporting Service")],
        [MockCell("Framework"), MockCell(".NET 10.0")],
    ]
    assert is_horizontal_two_column_table(prop_grid) is True

    # standard vertical two-column table should not be treated as horizontal
    vertical_grid = [
        [MockCell("Document Title", column_header=True), MockCell("Reference / Link", column_header=True)],
        [MockCell("Cheshire SRS"), MockCell("https://internal.gitlab.com/srs")],
        [MockCell("Cheshire Architecture"), MockCell("https://internal.gitlab.com/arch")],
    ]
    assert is_horizontal_two_column_table(vertical_grid) is False


def test_format_table_markdown_horizontal_table():
    """verify that horizontal property tables render with synthetic headers and preserve row 0 as data."""
    grid = [
        [MockCell("Application:"), MockCell("FinCEN Rule 17-B Serialization and Reporting Service")],
        [MockCell("Framework:"), MockCell(".NET 10.0")],
        [MockCell("Database:"), MockCell("SQL Server 2022")],
    ]
    table_bbox = BoundingBox(l=50.0, t=100.0, r=550.0, b=250.0, coord_origin=CoordOrigin.TOPLEFT)
    table_item = MockTableItem(grid, table_bbox, page_no=1)
    doc = MockDoc([])

    md, _ = _format_table_markdown(table_item, doc, last_header=None, is_continuation=False)
    lines = md.strip().split("\n")
    # headers should be property and value
    assert "Property" in lines[0]
    assert "Value" in lines[0]
    # row 0 should appear as first data row rather than header
    assert "Application:" in lines[2]
    assert "FinCEN Rule 17-B Serialization and Reporting Service" in lines[2]
    assert "Framework:" in lines[3]
    # table should have no empty cells
    assert _table_has_empty_cells(md) is False


def test_category_divider_row_detection_and_formatting():
    """verify category divider rows (e.g. others (specify)) are detected and prevent false empty cell findings."""
    divider_row = [MockCell("Others (specify)"), MockCell(""), MockCell(""), MockCell("")]
    assert _is_category_divider_row(divider_row, r_idx=2, num_cols=4) is True

    # numeric index with missing cells should not be treated as divider
    missing_data_row = [MockCell("2."), MockCell(""), MockCell(""), MockCell("")]
    assert _is_category_divider_row(missing_data_row, r_idx=2, num_cols=4) is False

    # full table containing a category divider row
    grid = [
        [MockCell("Name", column_header=True), MockCell("Hours", column_header=True), MockCell("Rate", column_header=True), MockCell("Total", column_header=True)],
        [MockCell("Alice"), MockCell("40"), MockCell("50"), MockCell("2000")],
        [MockCell("Others (specify)"), MockCell(""), MockCell(""), MockCell("")],
        [MockCell("Consultant"), MockCell("10"), MockCell("100"), MockCell("1000")],
    ]
    table_bbox = BoundingBox(l=50.0, t=100.0, r=550.0, b=300.0, coord_origin=CoordOrigin.TOPLEFT)
    table_item = MockTableItem(grid, table_bbox, page_no=1)
    doc = MockDoc([])

    md, _ = _format_table_markdown(table_item, doc, last_header=None, is_continuation=False)
    # verify that section divider annotations were placed in trailing cells
    assert "[Section Divider]" in md
    # empty cell detection should not flag this table as having missing data
    assert _table_has_empty_cells(md) is False


def test_row_zero_icon_detection():
    """verify that embedded icons located in row 0 are detected when text is empty."""
    pic_bbox = BoundingBox(l=60.0, t=105.0, r=80.0, b=125.0, coord_origin=CoordOrigin.TOPLEFT)
    pics = [MockPicture(pic_bbox, page_no=1)]
    cell_box = {"l": 50.0, "r": 150.0, "t": 100.0, "b": 130.0}

    # row 0 cell with empty text should detect embedded icon
    formatted = _format_cell_with_icons(
        cell_text="",
        cell_box=cell_box,
        has_cell_bounds=True,
        pics=pics,
        page_h=792.0,
        is_header_row=True,
    )
    assert formatted == ["[Embedded Icon]"]


def test_infer_cell_value_type_currencies_and_dates():
    """test type inferer"""
    # currencies with unicode sc
    assert _infer_cell_value_type("₱ 500.00") == "numeric"
    assert _infer_cell_value_type("฿ 1,200") == "numeric"
    assert _infer_cell_value_type("﷼ 750") == "numeric"
    assert _infer_cell_value_type("$100.50") == "numeric"
    # iso codes
    assert _infer_cell_value_type("AED 500") == "numeric"
    assert _infer_cell_value_type("1,000 SAR") == "numeric"
    assert _infer_cell_value_type("Php 250") == "numeric"
    # percent and float
    assert _infer_cell_value_type("40%") == "numeric"
    assert _infer_cell_value_type("40") == "numeric"
    # dates via dateutil
    assert _infer_cell_value_type("10-23") == "datetime"
    assert _infer_cell_value_type("October 23, 2026") == "datetime"
    assert _infer_cell_value_type("10:00 AM") == "datetime"
    # bools
    assert _infer_cell_value_type("true") == "boolean"
    assert _infer_cell_value_type("N/A") == "boolean"
    # text
    assert _infer_cell_value_type("John") == "text"
    assert _infer_cell_value_type("Contributor") == "text"


def test_is_horizontal_two_column_table_short_words_and_digits():
    """test short words and numbers table"""
    # no colons short numbers and mixed types
    grid = [
        [MockCell("Time-to-Work"), MockCell("40")],
        [MockCell("Contributor"), MockCell("John")],
        [MockCell("Start Date"), MockCell("10-23")],
    ]
    assert is_horizontal_two_column_table(grid) is True


def test_is_horizontal_two_column_table_long_col0_values():
    """test long col 0 descriptive metric names"""
    grid = [
        [MockCell("Time-to-Work"), MockCell("40")],
        [MockCell("Average Time Taken to Work (minutes)"), MockCell("60")],
        [MockCell("Amount Exerted to Finish Accumulated Work"), MockCell("10")],
    ]
    assert is_horizontal_two_column_table(grid) is True


def test_is_horizontal_two_column_table_nli_tier2():
    """test tier 2 nli model on text-only ambiguous table"""
    grid = [
        [MockCell("Contributor"), MockCell("John")],
        [MockCell("Sub-contributor"), MockCell("Alex")],
        [MockCell("Project Name"), MockCell("Genome Sequencing Tool")],
    ]

    # mock nli returning entailment for john is a contributor
    mock_nli_horizontal = lambda p, h: 0.92 if "John is a Contributor" in h else 0.1
    assert is_horizontal_two_column_table(grid, nli_evaluator=mock_nli_horizontal) is True

    # mock vertical table where role is not a contributor
    vertical_grid = [
        [MockCell("Contributor"), MockCell("Role")],
        [MockCell("John"), MockCell("Lead")],
    ]
    mock_nli_vertical = lambda p, h: 0.05
    assert is_horizontal_two_column_table(vertical_grid, nli_evaluator=mock_nli_vertical) is False

    # offline fallback using text length divergence
    assert is_horizontal_two_column_table(grid, nli_evaluator=None) is True


def test_detect_document_footer_top_mixed_text_and_table_footer():
    """Verify that _detect_document_footer_top handles footers composed of both text and tables."""
    class MockElementItem:
        def __init__(self, text: str, bbox: BoundingBox, label: str = "text"):
            self.text = text
            self.label = label
            self.prov = [MockProv(bbox, page_no=1)]

    # 1. Text disclaimer at y=620 (higher in footer stack)
    text_bbox = BoundingBox(l=50.0, t=620.0, r=550.0, b=650.0, coord_origin=CoordOrigin.TOPLEFT)
    text_item = MockElementItem("Classification: Strictly Confidential - Internal Use Only", text_bbox)

    # 2. Table at y=680 (lower in footer stack)
    table_grid = [
        [MockCell("Document ID: ASD-01"), MockCell("Version: 1.0"), MockCell("Page 1 of 5")]
    ]
    table_bbox = BoundingBox(l=50.0, t=680.0, r=550.0, b=720.0, coord_origin=CoordOrigin.TOPLEFT)
    table_item = MockTableItem(table_grid, table_bbox)

    doc = MockDoc([])
    doc.texts = [text_item]
    doc.tables = [table_item]
    doc.pages[1] = type("MockPage", (), {"size": type("MockSize", (), {"height": 792.0})()})()

    footer_top = _detect_document_footer_top(doc, page_h=792.0)
    # Headroom gives 620 - 10 = 610.0
    assert footer_top == 610.0

    # Both text and table items should be recognized as footer elements
    assert _is_footer_element(text_item, doc, page_h=792.0, footer_top=footer_top) is True
    assert _is_footer_element(table_item, doc, page_h=792.0, footer_top=footer_top) is True


def test_detect_document_footer_top_table_above_text_mixed_footer():
    """Verify mixed footer where multi-row table is positioned above text disclaimer."""
    class MockElementItem:
        def __init__(self, text: str, bbox: BoundingBox, label: str = "text"):
            self.text = text
            self.label = label
            self.prov = [MockProv(bbox, page_no=1)]

    # 1. Multi-row document control table starting at y=590
    table_grid = [
        [MockCell("Document Title: System Specification"), MockCell("Doc Owner: Architecture")],
        [MockCell("Document ID: SPEC-2024"), MockCell("Page 1 of 10")],
    ]
    table_bbox = BoundingBox(l=50.0, t=590.0, r=550.0, b=660.0, coord_origin=CoordOrigin.TOPLEFT)
    table_item = MockTableItem(table_grid, table_bbox)

    # 2. Text disclaimer below table at y=680
    text_bbox = BoundingBox(l=50.0, t=680.0, r=550.0, b=700.0, coord_origin=CoordOrigin.TOPLEFT)
    text_item = MockElementItem("All rights reserved. Proprietary information.", text_bbox)

    doc = MockDoc([])
    doc.tables = [table_item]
    doc.texts = [text_item]
    doc.pages[1] = type("MockPage", (), {"size": type("MockSize", (), {"height": 792.0})()})()

    footer_top = _detect_document_footer_top(doc, page_h=792.0)
    # Headroom gives 590 - 10 = 580.0
    assert footer_top == 580.0

    # Both table and text items should be detected as footer elements
    assert _is_footer_element(table_item, doc, page_h=792.0, footer_top=footer_top) is True
    assert _is_footer_element(text_item, doc, page_h=792.0, footer_top=footer_top) is True


def test_format_table_markdown_prunes_mixed_absorbed_footer_rows():
    """Verify that multiple absorbed footer rows (both table & text rows) are stripped."""
    grid = [
        [MockCell("Component", True), MockCell("Status", True)],
        [MockCell("AuthService"), MockCell("Active")],
        [MockCell("Document ID: SPEC-2024"), MockCell("Page 1 of 10")],
        [MockCell("Classification: Strictly Confidential"), MockCell("All rights reserved")],
    ]
    table_bbox = BoundingBox(l=50.0, t=500.0, r=550.0, b=740.0, coord_origin=CoordOrigin.TOPLEFT)
    item = MockTableItem(grid, table_bbox)
    doc = MockDoc([])
    doc.pages[1] = type("MockPage", (), {"size": type("MockSize", (), {"height": 792.0})()})()

    md, _ = _format_table_markdown(item, doc, last_header=None, is_continuation=False)
    # Legitimate data rows preserved
    assert "AuthService" in md
    assert "Active" in md
    # Both absorbed footer rows pruned
    assert "SPEC-2024" not in md
    assert "Strictly Confidential" not in md




