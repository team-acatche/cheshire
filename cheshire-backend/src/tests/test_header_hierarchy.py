"""
unit tests for header hierarchy resolution and sequence parsing.
all comments and docstrings in this module are strictly lowercase.
"""

from cheshire_configs.preprocessors.multistep.helpers import (
    ElementRef,
    EvaluationChunk,
    FigureRef,
    HeaderHierarchyResolver,
    HeaderToken,
    ImageBoundingBox,
    SeqType,
    _extract_section_key,
    _propagate_section_figures,
    merge_chunks,
    parse_header_token,
)
from docling_core.types.doc import BoundingBox, CoordOrigin


def test_parse_header_token_uppercase_delimiters():
    # verify parsing uppercase letters with different delimiters
    tok_dot = parse_header_token("A. Section Title")
    assert tok_dot.root_key == "A"
    assert tok_dot.prefix_label == "A"
    assert tok_dot.title == "Section Title"
    assert tok_dot.segments[0].kind == SeqType.upper_alpha

    tok_dash = parse_header_token("B - Another Title")
    assert tok_dash.root_key == "B"
    assert tok_dash.title == "Another Title"

    tok_paren = parse_header_token("(C) Parenthesized Title")
    assert tok_paren.root_key == "C"
    assert tok_paren.title == "Parenthesized Title"

    tok_prefix = parse_header_token("Section D. Structural Title")
    assert tok_prefix.root_key == "D"
    assert tok_prefix.title == "Structural Title"


def test_parse_header_token_lowercase_delimiters():
    # verify parsing lowercase letters with different delimiters
    tok_dot = parse_header_token("a. Subsection Title")
    assert tok_dot.root_key == "a"
    assert tok_dot.segments[0].kind == SeqType.lower_alpha
    assert tok_dot.title == "Subsection Title"

    tok_dash = parse_header_token("b - Detail Title")
    assert tok_dash.root_key == "b"
    assert tok_dash.title == "Detail Title"

    tok_paren = parse_header_token("(c) Subclause Title")
    assert tok_paren.root_key == "c"
    assert tok_paren.title == "Subclause Title"


def test_parse_header_token_numeric_delimiters():
    # verify parsing numbers with different delimiters
    tok_dot = parse_header_token("1. Numeric Title")
    assert tok_dot.root_key == "1"
    assert tok_dot.segments[0].kind == SeqType.numeric
    assert tok_dot.segments[0].val == 1
    assert tok_dot.title == "Numeric Title"

    tok_dash = parse_header_token("2 - Dashed Number")
    assert tok_dash.root_key == "2"

    tok_paren = parse_header_token("(3) Paren Number")
    assert tok_paren.root_key == "3"

    tok_space = parse_header_token("4 Standalone Number")
    assert tok_space.root_key == "4"
    assert tok_space.title == "Standalone Number"


def test_parse_header_token_compound_delimiters():
    # verify parsing dot, dash, and no-delimiter compound identifiers
    tok_dot = parse_header_token("E.1 Modules")
    assert tok_dot.root_key == "E"
    assert len(tok_dot.segments) == 2
    assert tok_dot.segments[0].raw == "E"
    assert tok_dot.segments[1].raw == "1"

    tok_dash = parse_header_token("E-2 Diagrams")
    assert tok_dash.root_key == "E"
    assert len(tok_dash.segments) == 2
    assert tok_dash.segments[1].raw == "2"

    tok_nodelim = parse_header_token("E3 Records")
    assert tok_nodelim.root_key == "E"
    assert len(tok_nodelim.segments) == 2
    assert tok_nodelim.segments[1].raw == "3"

    tok_multi = parse_header_token("1.2.3 Deep Subsection")
    assert tok_multi.root_key == "1"
    assert len(tok_multi.segments) == 3


def test_parse_header_token_roman_numerals():
    # verify parsing roman numerals
    tok_iv = parse_header_token("IV. System Considerations")
    assert tok_iv.root_key == "IV"
    assert tok_iv.segments[0].kind == SeqType.roman_upper
    assert tok_iv.segments[0].val == 4

    tok_lower_iii = parse_header_token("(iii) Sub-item")
    assert tok_lower_iii.root_key == "iii"
    assert tok_lower_iii.segments[0].kind == SeqType.roman_lower
    assert tok_lower_iii.segments[0].val == 3


def test_parse_header_token_unnumbered():
    # verify non-sequential descriptive headings are tagged unnumbered
    tok = parse_header_token("General Architecture and Guidelines")
    assert tok.is_unnumbered is True
    assert tok.root_key == ""
    assert tok.title == "General Architecture and Guidelines"


def test_hierarchy_resolver_user_example():
    # verify the exact user scenario: section e with subsections 1, 2, 3 followed by section f
    resolver = HeaderHierarchyResolver()

    b0 = resolver.process_heading("E. Processing Specifications")
    assert b0 == "E. Processing Specifications"
    assert resolver.get_root_key() == "E"
    assert resolver.get_root_heading() == "E. Processing Specifications"

    b1 = resolver.process_heading("1. Modules")
    assert b1 == "E. Processing Specifications - 1. Modules"
    assert resolver.get_root_key() == "E"

    b2 = resolver.process_heading("2. Diagrams")
    assert b2 == "E. Processing Specifications - 2. Diagrams"
    assert resolver.get_root_key() == "E"

    b3 = resolver.process_heading("3. Files and Records")
    assert b3 == "E. Processing Specifications - 3. Files and Records"
    assert resolver.get_root_key() == "E"

    bf = resolver.process_heading("F. System Considerations")
    assert bf == "F. System Considerations"
    assert resolver.get_root_key() == "F"
    assert resolver.get_root_heading() == "F. System Considerations"


def test_hierarchy_resolver_lowercase_parent_numeric_subsections():
    # verify lowercase parent section with numeric subsections
    resolver = HeaderHierarchyResolver()

    b1 = resolver.process_heading("a. Ingestion Pipeline")
    assert b1 == "a. Ingestion Pipeline"
    assert resolver.get_root_key() == "a"

    b2 = resolver.process_heading("1. Source Connectors")
    assert b2 == "a. Ingestion Pipeline - 1. Source Connectors"
    assert resolver.get_root_key() == "a"

    b3 = resolver.process_heading("2. Validation Rules")
    assert b3 == "a. Ingestion Pipeline - 2. Validation Rules"
    assert resolver.get_root_key() == "a"

    b4 = resolver.process_heading("b. Transformation Pipeline")
    assert b4 == "b. Transformation Pipeline"
    assert resolver.get_root_key() == "b"


def test_hierarchy_resolver_numeric_parent_lowercase_subsections():
    # verify numeric parent section with lowercase letter subsections
    resolver = HeaderHierarchyResolver()

    b1 = resolver.process_heading("1. Core Infrastructure")
    assert b1 == "1. Core Infrastructure"
    assert resolver.get_root_key() == "1"

    b2 = resolver.process_heading("a. Network Topology")
    assert b2 == "1. Core Infrastructure - a. Network Topology"
    assert resolver.get_root_key() == "1"

    b3 = resolver.process_heading("b. Security Firewalls")
    assert b3 == "1. Core Infrastructure - b. Security Firewalls"
    assert resolver.get_root_key() == "1"

    b4 = resolver.process_heading("2. Application Layer")
    assert b4 == "2. Application Layer"
    assert resolver.get_root_key() == "2"


def test_hierarchy_resolver_compound_nesting():
    # verify compound identifiers nesting and sibling replacement
    resolver = HeaderHierarchyResolver()

    b1 = resolver.process_heading("1. Main Section")
    assert b1 == "1. Main Section"

    b1_1 = resolver.process_heading("1.1 First Child")
    assert b1_1 == "1. Main Section - 1.1 First Child"

    b1_2 = resolver.process_heading("1.2 Second Child")
    assert b1_2 == "1. Main Section - 1.2 Second Child"

    b2 = resolver.process_heading("2. Next Main Section")
    assert b2 == "2. Next Main Section"


def test_hierarchy_resolver_skipped_numbers():
    # verify non-consecutive numbers are recognized as siblings rather than children
    resolver = HeaderHierarchyResolver()

    resolver.process_heading("E. Processing Specifications")
    resolver.process_heading("1. Modules")
    # section 2 was deleted; section 3 appears directly
    b3 = resolver.process_heading("3. Files and Records")
    assert b3 == "E. Processing Specifications - 3. Files and Records"
    assert resolver.get_root_key() == "E"


def test_hierarchy_resolver_unnumbered_headers():
    # verify unnumbered headings attach as leaves without corrupting sequence state
    resolver = HeaderHierarchyResolver()

    resolver.process_heading("E. Processing Specifications")
    b_un = resolver.process_heading("Architecture Overview")
    assert b_un == "E. Processing Specifications - Architecture Overview"

    b1 = resolver.process_heading("1. Modules")
    assert b1 == "E. Processing Specifications - 1. Modules"


def test_extract_section_key_compatibility():
    # verify _extract_section_key correctly resolves root keys across variations
    assert _extract_section_key("E. Processing Specifications") == "E"
    assert _extract_section_key("E. Processing Specifications - 1. Modules") == "E"
    assert _extract_section_key("a. Overview - 1. Setup") == "a"
    assert _extract_section_key("1. Overview") == "1"
    assert _extract_section_key("E-1 Modules") == "E"
    assert _extract_section_key("E1 Modules") == "E"
    assert _extract_section_key("Section F. Availability") == "F"


def test_merge_chunks_with_alphanumeric_subsections():
    # verify contiguous chunks with alphanumeric subsections merge under common parent
    dummy_bbox_image = ImageBoundingBox(x1=0, y1=0, x2=10, y2=10)
    dummy_bbox_pdf = BoundingBox(l=0, t=0, r=10, b=10, coord_origin=CoordOrigin.TOPLEFT)

    elem1 = ElementRef(
        element_id="elem_1",
        label="paragraph",
        page_number=5,
        bbox_image_px=dummy_bbox_image,
        bbox_pdf=dummy_bbox_pdf,
        text_excerpt="Modules specifications.",
    )
    elem2 = ElementRef(
        element_id="elem_2",
        label="paragraph",
        page_number=5,
        bbox_image_px=dummy_bbox_image,
        bbox_pdf=dummy_bbox_pdf,
        text_excerpt="Diagrams specifications.",
    )

    chunk1 = EvaluationChunk(
        chunk_id="c1",
        heading="E. Processing Specifications - 1. Modules",
        page_range=(5, 5),
        structured_text="[ID:elem_1|paragraph|p5]\nModules specifications.",
        element_refs=[elem1],
        figures=[],
    )
    chunk2 = EvaluationChunk(
        chunk_id="c2",
        heading="E. Processing Specifications - 2. Diagrams",
        page_range=(5, 5),
        structured_text="[ID:elem_2|paragraph|p5]\nDiagrams specifications.",
        element_refs=[elem2],
        figures=[],
    )

    merged = merge_chunks([chunk1, chunk2], max_chars=1000)
    assert len(merged) == 1
    # parent heading preserved on merged chunk
    assert merged[0].heading == "E. Processing Specifications"
    assert len(merged[0].element_refs) == 2
    assert "Modules specifications" in merged[0].structured_text
    assert "Diagrams specifications" in merged[0].structured_text


def test_propagate_section_figures_across_mixed_subsections():
    # verify figures attached to subsection 2 are shared with subsection 1 under section e
    dummy_bbox_image = ImageBoundingBox(x1=0, y1=0, x2=10, y2=10)
    dummy_bbox_pdf = BoundingBox(l=0, t=0, r=10, b=10, coord_origin=CoordOrigin.TOPLEFT)

    fig = FigureRef(
        figure_id="fig_e2",
        page_number=6,
        bbox_image_px=dummy_bbox_image,
        bbox_pdf=dummy_bbox_pdf,
        base64_png="data:image/png;base64,sample",
    )

    chunk1 = EvaluationChunk(
        chunk_id="c1",
        heading="E. Processing Specifications - 1. Modules",
        page_range=(5, 5),
        structured_text="See diagram in section 2.",
        element_refs=[],
        figures=[],
    )
    chunk2 = EvaluationChunk(
        chunk_id="c2",
        heading="E. Processing Specifications - 2. Diagrams",
        page_range=(6, 6),
        structured_text="Diagram detail.",
        element_refs=[],
        figures=[fig],
    )

    chunks = [chunk1, chunk2]
    _propagate_section_figures(chunks)

    # chunk 1 now sees the figure from subsection 2
    assert len(chunks[0].figures) == 1
    assert chunks[0].figures[0].figure_id == "fig_e2"
