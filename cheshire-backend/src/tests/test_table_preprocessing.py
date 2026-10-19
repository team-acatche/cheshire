from docling_core.types.doc import BoundingBox, CoordOrigin
from docling_core.types.doc.document import DoclingDocument
from cheshire_configs.preprocessors.multistep.helpers import (
    DEFAULT_COL_WIDTH_PX,
    DEFAULT_ROW_HEIGHT_PX,
    _detect_compound_header_split,
    _format_table_markdown,
    _table_has_empty_cells,
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
