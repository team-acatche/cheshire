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
    _extract_heading_from_text,
    _extract_section_key,
    _propagate_section_figures,
    merge_chunks,
    parse_header_token,
    promote_heuristic_headings,
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


def test_hierarchy_resolver_idempotent_repeated_headers():
    # verify calling process_heading repeatedly with the exact same header does not duplicate
    resolver = HeaderHierarchyResolver()

    b1 = resolver.process_heading("E. Recommendations")
    assert b1 == "E. Recommendations"
    assert len(resolver.stack) == 1

    b2 = resolver.process_heading("E. Recommendations")
    assert b2 == "E. Recommendations"
    assert len(resolver.stack) == 1

    b3 = resolver.process_heading("E. Recommendations")
    assert b3 == "E. Recommendations"
    assert len(resolver.stack) == 1

    b4 = resolver.process_heading("E. Recommendations")
    assert b4 == "E. Recommendations"
    assert len(resolver.stack) == 1


def test_hierarchy_resolver_chunk_repetition_and_subheaders():
    # verify chunk heading paths across multiple chunks do not duplicate headers and advance root
    resolver = HeaderHierarchyResolver()

    # chunk 1: section e
    c1 = resolver.process_headings(["E. Recommendations"])
    assert c1 == "E. Recommendations"
    assert resolver.get_root_key() == "E"
    assert len(resolver.stack) == 1

    # chunk 2: section e repeated across chunks
    c2 = resolver.process_headings(["E. Recommendations"])
    assert c2 == "E. Recommendations"
    assert resolver.get_root_key() == "E"
    assert len(resolver.stack) == 1

    # chunk 3: subheader 1 under section e
    c3 = resolver.process_headings(["E. Recommendations", "1. Modules"])
    assert c3 == "E. Recommendations - 1. Modules"
    assert resolver.get_root_key() == "E"
    assert len(resolver.stack) == 2

    # chunk 4: subheader 1 repeated across chunks
    c4 = resolver.process_headings(["E. Recommendations", "1. Modules"])
    assert c4 == "E. Recommendations - 1. Modules"
    assert resolver.get_root_key() == "E"
    assert len(resolver.stack) == 2

    # chunk 5: sibling subheader 2 under section e
    c5 = resolver.process_headings(["E. Recommendations", "2. Diagrams"])
    assert c5 == "E. Recommendations - 2. Diagrams"
    assert resolver.get_root_key() == "E"
    assert len(resolver.stack) == 2
    assert resolver.stack[1].token.prefix_label == "2"

    # chunk 6: advancing to section f resets root cleanly and does not stick to e
    c6 = resolver.process_headings(["F. System Considerations"])
    assert c6 == "F. System Considerations"
    assert resolver.get_root_key() == "F"
    assert resolver.get_root_heading() == "F. System Considerations"
    assert len(resolver.stack) == 1

    # chunk 7: section f repeated across chunks
    c7 = resolver.process_headings(["F. System Considerations"])
    assert c7 == "F. System Considerations"
    assert resolver.get_root_key() == "F"
    assert len(resolver.stack) == 1


def test_hierarchy_resolver_flattened_docling_leaf_headings():
    # verify docling providing only leaf headings preserves parent hierarchy and advances correctly
    resolver = HeaderHierarchyResolver()

    c1 = resolver.process_heading("E. Recommendations")
    assert c1 == "E. Recommendations"

    c2 = resolver.process_heading("1. Modules")
    assert c2 == "E. Recommendations - 1. Modules"
    assert resolver.get_root_key() == "E"

    # repeated chunk on same leaf
    c3 = resolver.process_heading("1. Modules")
    assert c3 == "E. Recommendations - 1. Modules"
    assert len(resolver.stack) == 2

    c4 = resolver.process_heading("2. Diagrams")
    assert c4 == "E. Recommendations - 2. Diagrams"
    assert resolver.get_root_key() == "E"

    c5 = resolver.process_heading("F. System Considerations")
    assert c5 == "F. System Considerations"
    assert resolver.get_root_key() == "F"
    assert len(resolver.stack) == 1


def test_extract_section_key_compatibility():
    # verify _extract_section_key correctly resolves compound and root keys across variations
    assert _extract_section_key("E. Processing Specifications") == "E"
    assert _extract_section_key("E. Processing Specifications - 1. Modules") == "E/1"
    assert _extract_section_key("a. Overview - 1. Setup") == "a/1"
    assert _extract_section_key("1. Overview") == "1"
    assert _extract_section_key("E-1 Modules") == "E/1"
    assert _extract_section_key("E1 Modules") == "E/1"
    assert _extract_section_key("Section F. Availability") == "F"


def test_merge_chunks_with_alphanumeric_subsections():
    # verify contiguous chunks with distinct subsections remain separate
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
    # Distinct subsections E/1 and E/2 must remain separate chunks
    assert len(merged) == 2
    assert merged[0].heading == "E. Processing Specifications - 1. Modules"
    assert merged[1].heading == "E. Processing Specifications - 2. Diagrams"

    # Chunks from the SAME subsection do merge together
    chunk1_cont = EvaluationChunk(
        chunk_id="c1_cont",
        heading="E. Processing Specifications - 1. Modules",
        page_range=(5, 6),
        structured_text="[ID:elem_1b|paragraph|p6]\nMore modules specifications.",
        element_refs=[elem1],
        figures=[],
    )
    merged_same = merge_chunks([chunk1, chunk1_cont], max_chars=1000)
    assert len(merged_same) == 1
    assert merged_same[0].heading == "E. Processing Specifications - 1. Modules"
    assert merged_same[0].page_range == (5, 6)


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


def test_extract_heading_from_text_patterns():
    # verify extraction of outline section headers and subsections from raw text lines
    assert _extract_heading_from_text("E. Processing Specifications") == "E. Processing Specifications"
    assert _extract_heading_from_text("E. Processing Specifications:\nIntro text") == "E. Processing Specifications"
    assert _extract_heading_from_text("1. Modules") == "1. Modules"
    assert _extract_heading_from_text("2. Diagrams") == "2. Diagrams"
    assert _extract_heading_from_text("3. Files and Records") == "3. Files and Records"
    assert _extract_heading_from_text("4. Reports") == "4. Reports"
    assert _extract_heading_from_text("5. Parameter and Lookup Files") == "5. Parameter and Lookup Files"
    assert _extract_heading_from_text("Section D. Technology Stack Requirements") == "Section D. Technology Stack Requirements"
    assert _extract_heading_from_text("1.1 Handler Layer") == "1.1 Handler Layer"
    assert _extract_heading_from_text("I. Executive Summary") == "I. Executive Summary"
    assert _extract_heading_from_text("Appendix A - Revision History") == "Appendix A - Revision History"


def test_extract_heading_from_text_rejects_non_headings():
    # verify non-heading text lines are rejected
    assert _extract_heading_from_text("JVM/Go GC pause times during large XML serialization cycles.") is None
    assert _extract_heading_from_text("A. All user passwords must be hashed before storage in the database.") is None
    assert _extract_heading_from_text("Table: products") is None
    assert _extract_heading_from_text("Specifications: Outbound Status Code from the gateway.") is None
    assert _extract_heading_from_text("• Bullet point text in document") is None
    assert _extract_heading_from_text("1. Deliver a functioning website within a four-month development period.") is None


def test_hierarchy_resolver_recovers_section_e_when_subsections_follow_section_d():
    # verify resolver advances to section e when major section e arrives after section d
    resolver = HeaderHierarchyResolver()
    b_d = resolver.process_heading("D. Technology Stack Requirements")
    assert b_d == "D. Technology Stack Requirements"
    assert resolver.get_root_key() == "D"

    # major section e arrives and advances root scope from d to e
    b_e = resolver.process_heading("E. Processing Specifications")
    assert b_e == "E. Processing Specifications"
    assert resolver.get_root_key() == "E"

    # subheader 1 subordinates under active section e
    b_mod = resolver.process_heading("1. Modules")
    assert b_mod == "E. Processing Specifications - 1. Modules"
    assert resolver.get_root_key() == "E"

    # sibling subheader 2 continues under section e
    b_diag = resolver.process_heading("2. Diagrams")
    assert b_diag == "E. Processing Specifications - 2. Diagrams"
    assert resolver.get_root_key() == "E"


def test_merge_chunks_separates_section_d_and_section_e():
    # verify section d terminates at page 6 and does not absorb section e chunks (pages 7-13)
    chunk_d = EvaluationChunk(
        chunk_id="c0",
        heading="D. Technology Stack Requirements",
        page_range=(5, 6),
        structured_text="Tech stack details on pages 5 and 6",
        element_refs=[],
        figures=[],
    )
    chunk_e1 = EvaluationChunk(
        chunk_id="c1",
        heading="E. Processing Specifications - 1. Modules",
        page_range=(7, 7),
        structured_text="Module specs on page 7",
        element_refs=[],
        figures=[],
    )
    chunk_e2 = EvaluationChunk(
        chunk_id="c2",
        heading="E. Processing Specifications - 2. Diagrams",
        page_range=(7, 8),
        structured_text="Diagram specs on pages 7 and 8",
        element_refs=[],
        figures=[],
    )
    chunk_e3 = EvaluationChunk(
        chunk_id="c3",
        heading="E. Processing Specifications - 3. Files and Records",
        page_range=(8, 9),
        structured_text="Files specs on pages 8 and 9",
        element_refs=[],
        figures=[],
    )
    chunk_e4 = EvaluationChunk(
        chunk_id="c4",
        heading="E. Processing Specifications - 4. Reports",
        page_range=(9, 10),
        structured_text="Reports specs on pages 9 and 10",
        element_refs=[],
        figures=[],
    )
    chunk_e5 = EvaluationChunk(
        chunk_id="c5",
        heading="E. Processing Specifications - 5. Parameter and Lookup Files",
        page_range=(10, 13),
        structured_text="Lookup files specs on pages 10 to 13",
        element_refs=[],
        figures=[],
    )

    merged = merge_chunks([chunk_d, chunk_e1, chunk_e2, chunk_e3, chunk_e4, chunk_e5])

    # section d and each section e subsection remain separate chunks with correct page bounds
    assert len(merged) == 6
    assert merged[0].heading == "D. Technology Stack Requirements"
    assert merged[0].page_range == (5, 6)
    assert merged[1].heading == "E. Processing Specifications - 1. Modules"
    assert merged[1].page_range == (7, 7)
    assert merged[2].heading == "E. Processing Specifications - 2. Diagrams"
    assert merged[2].page_range == (7, 8)
    assert merged[3].heading == "E. Processing Specifications - 3. Files and Records"
    assert merged[3].page_range == (8, 9)
    assert merged[4].heading == "E. Processing Specifications - 4. Reports"
    assert merged[4].page_range == (9, 10)
    assert merged[5].heading == "E. Processing Specifications - 5. Parameter and Lookup Files"
    assert merged[5].page_range == (10, 13)


def test_promote_heuristic_headings_on_mock_document():
    # verify promote_heuristic_headings detects misclassified paragraph headings in mock doc
    class MockProv:
        def __init__(self, page_no):
            self.page_no = page_no

    class MockItem:
        def __init__(self, label, text, self_ref, page_no):
            self.label = label
            self.text = text
            self.self_ref = self_ref
            self.prov = [MockProv(page_no)]

    class MockDoc:
        def __init__(self, items):
            self.items = items
            self.texts = items

        def iterate_items(self):
            for item in self.items:
                yield item, 0

    items = [
        MockItem("section_header", "D. Technology Stack Requirements", "#/texts/0", 5),
        MockItem("paragraph", "Tech stack body text", "#/texts/1", 5),
        MockItem("paragraph", "E. Processing Specifications", "#/texts/2", 7),
        MockItem("paragraph", "1. Modules", "#/texts/3", 7),
        MockItem("paragraph", "Regular module description paragraph.", "#/texts/4", 7),
    ]
    doc = MockDoc(items)

    promoted = promote_heuristic_headings(doc)
    assert "E. Processing Specifications" in promoted
    assert "1. Modules" in promoted

    assert items[0].label == "section_header"
    assert items[1].label == "paragraph"
    assert items[2].label in ("section_header", "section_heading")
    assert items[3].label in ("section_header", "section_heading")
    assert items[4].label == "paragraph"


def test_hierarchy_resolver_scientific_decimal_outline():
    # verify decimal hierarchy resolution for scientific / academic papers
    resolver = HeaderHierarchyResolver()
    assert resolver.process_heading("1. Introduction") == "1. Introduction"
    assert resolver.get_root_key() == "1"

    assert resolver.process_heading("1.1 Background") == "1. Introduction - 1.1 Background"
    assert resolver.get_root_key() == "1"

    assert resolver.process_heading("1.2 Prior Work") == "1. Introduction - 1.2 Prior Work"
    assert resolver.get_root_key() == "1"

    # advance to section 2
    assert resolver.process_heading("2. Methodology") == "2. Methodology"
    assert resolver.get_root_key() == "2"

    assert resolver.process_heading("2.1 Data Collection") == "2. Methodology - 2.1 Data Collection"
    assert resolver.get_root_key() == "2"


def test_hierarchy_resolver_legal_articles_and_sections():
    # verify structural prefix hierarchies for legal contracts and governance documents
    resolver = HeaderHierarchyResolver()
    assert resolver.process_heading("Article I - Definitions") == "Article I - Definitions"
    assert resolver.get_root_key() == "I"

    assert resolver.process_heading("Section 1.1 Party Obligations") == "Article I - Definitions - Section 1.1 Party Obligations"
    assert resolver.get_root_key() == "I"

    # advance to article ii
    assert resolver.process_heading("Article II - Payment Terms") == "Article II - Payment Terms"
    assert resolver.get_root_key() == "II"

    assert resolver.process_heading("Section 2.1 Invoicing") == "Article II - Payment Terms - Section 2.1 Invoicing"
    assert resolver.get_root_key() == "II"


def test_hierarchy_resolver_sequence_reset_across_parents():
    # verify that subordinate sequences reset cleanly when transitioning across major parents
    resolver = HeaderHierarchyResolver()
    resolver.process_heading("A. First Major Division")
    resolver.process_heading("1. Item One")
    resolver.process_heading("2. Item Two")
    assert resolver.get_current_breadcrumb() == "A. First Major Division - 2. Item Two"

    # new parent division b
    resolver.process_heading("B. Second Major Division")
    assert resolver.get_root_key() == "B"
    assert resolver.get_current_breadcrumb() == "B. Second Major Division"

    # subordinate sequence restarts at 1 under b
    resolver.process_heading("1. Item One")
    assert resolver.get_current_breadcrumb() == "B. Second Major Division - 1. Item One"
    assert resolver.get_root_key() == "B"


def test_no_wordlists_in_helper_modules():
    # verify that helper modules contain zero hardcoded section lists, dictionaries, or document maps
    import inspect
    from cheshire_configs.preprocessors.multistep import helpers

    for name in dir(helpers):
        assert not name.startswith("_KNOWN_"), f"Hardcoded wordlist {name} found in helpers!"
        assert not name.endswith("_MAP"), f"Hardcoded mapping {name} found in helpers!"

    # verify hierarchy module has zero hardcoded section titles or document-specific constants
    from cheshire_configs.preprocessors.multistep.helpers import hierarchy
    hierarchy_src = inspect.getsource(hierarchy).lower()
    assert "_known" not in hierarchy_src
    assert "sentrobank" not in hierarchy_src
    assert "processing specifications" not in hierarchy_src
    assert "technology stack" not in hierarchy_src


def test_extract_heading_compound_and_multiline_patterns():
    # verify extraction of compound outlines, spaced dashes, standalone sections, and multiline headers
    assert _extract_heading_from_text("B - System Architecture") == "B - System Architecture"
    assert _extract_heading_from_text("B – System Architecture") == "B – System Architecture"
    assert _extract_heading_from_text("Section B") == "Section B"
    assert _extract_heading_from_text("SECTION B") == "SECTION B"
    assert _extract_heading_from_text("Section B: System Architecture") == "Section B: System Architecture"
    assert _extract_heading_from_text("B.\nSystem Architecture") == "B. System Architecture"
    assert _extract_heading_from_text("E.1 Modules") == "E.1 Modules"
    assert _extract_heading_from_text("E.2 Database Design") == "E.2 Database Design"
    assert _extract_heading_from_text("E.3 Routing & Form Contracts") == "E.3 Routing & Form Contracts"
    assert _extract_heading_from_text("E.4 Process Flow") == "E.4 Process Flow"
    assert _extract_heading_from_text("E.5 Security Considerations") == "E.5 Security Considerations"


def test_resolver_major_advance_closes_previous_root():
    # verify that when an advancing major section or compound outline arrives, it closes the previous root
    resolver = HeaderHierarchyResolver()
    assert resolver.process_heading("D. Technology Stack Requirements") == "D. Technology Stack Requirements"
    assert resolver.get_root_key() == "D"

    # e.1 arrives without a standalone section e
    assert resolver.process_heading("E.1 Modules") == "E.1 Modules"
    assert resolver.get_root_key() == "E"

    assert resolver.process_heading("E.2 Database Design") == "E.2 Database Design"
    assert resolver.get_root_key() == "E"

    assert resolver.process_heading("E.3 Routing & Form Contracts") == "E.3 Routing & Form Contracts"
    assert resolver.get_root_key() == "E"


def test_merge_chunks_keeps_section_a_and_section_b_separated():
    # verify that section a (p3) and section b (p4) are never merged into p3-4
    c_a = EvaluationChunk(
        chunk_id="chunk_0",
        heading="A. Overview",
        page_range=(3, 3),
        structured_text="[ID:#/texts/1|paragraph|p3]\nSection A overview content",
        element_refs=[],
        figures=[],
    )
    c_b = EvaluationChunk(
        chunk_id="chunk_1",
        heading="B. System Architecture",
        page_range=(4, 4),
        structured_text="[ID:#/texts/2|paragraph|p4]\nSection B architecture content",
        element_refs=[],
        figures=[],
    )

    merged = merge_chunks([c_a, c_b])
    assert len(merged) == 2
    assert merged[0].heading == "A. Overview"
    assert merged[0].page_range == (3, 3)
    assert merged[1].heading == "B. System Architecture"
    assert merged[1].page_range == (4, 4)


def test_merge_chunks_section_d_and_e_subsections_boundary():
    # verify that section d (p5-6) does not merge with section e subsections (p7-13)
    c_d = EvaluationChunk(
        chunk_id="chunk_d",
        heading="D. Technology Stack Requirements",
        page_range=(5, 6),
        structured_text="[ID:#/texts/10|paragraph|p5]\nSection D technology stack requirements",
        element_refs=[],
        figures=[],
    )
    c_e1 = EvaluationChunk(
        chunk_id="chunk_e1",
        heading="E.1 Modules",
        page_range=(7, 7),
        structured_text="[ID:#/texts/11|paragraph|p7]\n" + ("E.1 modules content. " * 200),  # ~4300 chars
        element_refs=[],
        figures=[],
    )
    c_e2 = EvaluationChunk(
        chunk_id="chunk_e2",
        heading="E.2 Database Design",
        page_range=(7, 9),
        structured_text="[ID:#/texts/12|paragraph|p8]\n" + ("E.2 database design content. " * 200),  # ~5700 chars
        element_refs=[],
        figures=[],
    )
    c_e3 = EvaluationChunk(
        chunk_id="chunk_e3",
        heading="E.3 Routing & Form Contracts",
        page_range=(9, 10),
        structured_text="[ID:#/texts/13|paragraph|p9]\n" + ("E.3 routing content. " * 350),  # ~7100 chars
        element_refs=[],
        figures=[],
    )
    c_e45 = EvaluationChunk(
        chunk_id="chunk_e45",
        heading="E.4 Process Flow",
        page_range=(10, 11),
        structured_text="[ID:#/texts/14|paragraph|p10]\n" + ("E.4 flow content. " * 200),  # ~3500 chars
        element_refs=[],
        figures=[],
    )

    merged = merge_chunks([c_d, c_e1, c_e2, c_e3, c_e45], max_chars=16000)

    # c_d and each subsection remain separate chunks (distinct compound keys E/1, E/2, E/3, E/4)
    assert len(merged) == 5
    assert merged[0].heading == "D. Technology Stack Requirements"
    assert merged[0].page_range == (5, 6)
    assert merged[1].heading == "E.1 Modules"
    assert merged[1].page_range == (7, 7)
    assert merged[2].heading == "E.2 Database Design"
    assert merged[2].page_range == (7, 9)
    assert merged[3].heading == "E.3 Routing & Form Contracts"
    assert merged[3].page_range == (9, 10)
    assert merged[4].heading == "E.4 Process Flow"
    assert merged[4].page_range == (10, 11)


def test_build_chunks_splits_across_section_header_boundary():
    # verify that build_chunks splits when two sections are in the same raw chunk
    from docling_core.types.doc.document import DocItemLabel
    from cheshire_configs.preprocessors.multistep.helpers import build_chunks

    class MockItem:
        def __init__(self, ref):
            self.self_ref = ref

    class MockDocChunk:
        def __init__(self, doc_items):
            class Meta:
                pass
            self.meta = Meta()
            self.meta.doc_items = doc_items
            self.meta.headings = []

    class MockChunker:
        def chunk(self, doc):
            # returns a single chunk containing elements from page 3 (Section A) and page 4 (Section B)
            return [MockDocChunk([
                MockItem("#/texts/1"),
                MockItem("#/texts/2"),
                MockItem("#/texts/3"),
                MockItem("#/texts/4"),
            ])]

    class MockDoc:
        def __init__(self):
            self.pictures = []
            self.pages = {}
            self.texts = []

        def iterate_items(self):
            return []

    # create element lookup items
    dummy_img = ImageBoundingBox(x1=0, y1=0, x2=10, y2=10)
    dummy_pdf = BoundingBox(l=0, t=0, r=10, b=10, coord_origin=CoordOrigin.TOPLEFT)
    el1 = ElementRef(element_id="#/texts/1", label="section_header", text_excerpt="A. Overview", page_number=3, bbox_image_px=dummy_img, bbox_pdf=dummy_pdf)
    el2 = ElementRef(element_id="#/texts/2", label="paragraph", text_excerpt="Overview content", page_number=3, bbox_image_px=dummy_img, bbox_pdf=dummy_pdf)
    el3 = ElementRef(element_id="#/texts/3", label="section_header", text_excerpt="B. System Architecture", page_number=4, bbox_image_px=dummy_img, bbox_pdf=dummy_pdf)
    el4 = ElementRef(element_id="#/texts/4", label="paragraph", text_excerpt="Architecture content", page_number=4, bbox_image_px=dummy_img, bbox_pdf=dummy_pdf)

    # mock build_element_lookup and build_figure_lookup
    import cheshire_configs.preprocessors.multistep.helpers.chunking as ch_mod
    orig_build_el = ch_mod._build_element_lookup
    orig_build_fig = ch_mod._build_figure_lookup
    try:
        ch_mod._build_element_lookup = lambda *a, **k: {
            "#/texts/1": el1,
            "#/texts/2": el2,
            "#/texts/3": el3,
            "#/texts/4": el4,
        }
        ch_mod._build_figure_lookup = lambda *a, **k: {}

        chunks = ch_mod.build_chunks(MockDoc(), None, MockChunker())
        assert len(chunks) == 2
        assert chunks[0].heading == "A. Overview"
        assert chunks[0].page_range == (3, 3)
        assert chunks[1].heading == "B. System Architecture"
        assert chunks[1].page_range == (4, 4)
    finally:
        ch_mod._build_element_lookup = orig_build_el
        ch_mod._build_figure_lookup = orig_build_fig


def test_horizontal_pair_stitching_cover_block():
    """Verify that _find_horizontal_pair pairs horizontally aligned labels and values on the same page."""
    from cheshire_configs.preprocessors.multistep.helpers.chunking import _find_horizontal_pair

    dummy_img = ImageBoundingBox(x1=0, y1=0, x2=10, y2=10)
    # Label element 'Primary RSC:' at x in [50, 150], y in [200, 220]
    bbox_lbl = BoundingBox(l=50.0, t=200.0, r=150.0, b=220.0, coord_origin=CoordOrigin.TOPLEFT)
    el_lbl = ElementRef(
        element_id="#/texts/1",
        label="paragraph",
        text_excerpt="Primary RSC:",
        page_number=1,
        bbox_image_px=dummy_img,
        bbox_pdf=bbox_lbl,
    )

    # Value element 'PID-0015 AWV...' at x in [180, 500], y in [200, 220]
    bbox_val = BoundingBox(l=180.0, t=200.0, r=500.0, b=220.0, coord_origin=CoordOrigin.TOPLEFT)
    el_val = ElementRef(
        element_id="#/texts/2",
        label="paragraph",
        text_excerpt="PID-0015 AWV Serialization and Reporting of Rule 17-B ISAD",
        page_number=1,
        bbox_image_px=dummy_img,
        bbox_pdf=bbox_val,
    )

    # Distant / different line element
    bbox_other = BoundingBox(l=180.0, t=300.0, r=500.0, b=320.0, coord_origin=CoordOrigin.TOPLEFT)
    el_other = ElementRef(
        element_id="#/texts/3",
        label="paragraph",
        text_excerpt="Unrelated content",
        page_number=1,
        bbox_image_px=dummy_img,
        bbox_pdf=bbox_other,
    )

    all_elems = [el_lbl, el_val, el_other]
    matched = _find_horizontal_pair(el_lbl, all_elems)
    assert matched is not None
    assert matched.element_id == "#/texts/2"
    assert "PID-0015" in matched.text_excerpt


def test_is_stale_heading_detects_regressions_and_allows_advancement():
    """Verify that HeaderHierarchyResolver detects stale regressive headings without wordlists."""
    resolver = HeaderHierarchyResolver()
    resolver.process_heading("G. Security Considerations")

    # Regressing to subsection 3 from earlier section is stale
    assert resolver.is_stale_heading("3. Files and Records") is True
    assert resolver.is_stale_heading("4. Reports") is True

    # Same heading or advancing major section is not stale
    assert resolver.is_stale_heading("G. Security Considerations") is False
    assert resolver.is_stale_heading("H. Appendices") is False

    # Under Section E at subsection 5, subsection 3 is stale, but 6 is not
    resolver_e = HeaderHierarchyResolver()
    resolver_e.process_heading("E. Processing Specifications")
    resolver_e.process_heading("5. Parameter and Lookup Files")

    assert resolver_e.is_stale_heading("3. Files and Records") is True
    assert resolver_e.is_stale_heading("6. Others") is False
    assert resolver_e.is_stale_heading("F. System Considerations") is False


def test_build_document_index_table_enrichment():
    """Verify that document_index['tables'] contains headers and row summaries for inner table visibility."""
    from cheshire_configs.preprocessors.multistep.helpers.indexing import build_document_index
    from types import SimpleNamespace

    class MockCell:
        def __init__(self, text):
            self.text = text

    grid = [
        [MockCell("Diagram"), MockCell("Attachment")],
        [MockCell("Network Diagram"), MockCell("AWV Compliant Reporting Service Network Diagram.pdf")],
        [MockCell("Process Flow Diagram – Serialization and Reporting Service"), MockCell("PID-0015 Serialization and Reporting Process Flow Diagram.pdf")],
    ]

    mock_table = SimpleNamespace(
        self_ref="#/tables/11",
        label="table",
        data=SimpleNamespace(grid=grid),
        prov=[SimpleNamespace(page_no=5, bbox=BoundingBox(l=0, t=0, r=100, b=100, coord_origin=CoordOrigin.TOPLEFT))],
    )

    mock_doc = SimpleNamespace(
        iterate_items=lambda **kwargs: [(mock_table, 0)],
        pages={5: SimpleNamespace(size=SimpleNamespace(height=1000.0))},
        pictures=[],
        texts=[],
    )

    idx = build_document_index(mock_doc)
    assert len(idx["tables"]) == 1
    t = idx["tables"][0]
    assert t["headers"] == ["Diagram", "Attachment"]
    assert len(t["rows"]) == 2
    assert "Process Flow Diagram" in t["rows"][1]
    assert len(idx["diagram_documents"]) == 2
    assert any("Process Flow Diagram" in d["name"] for d in idx["diagram_documents"])


def test_hierarchy_resolver_same_level_title_update():
    """Verify that same-index sections update title rather than chaining or nesting."""
    resolver = HeaderHierarchyResolver()
    resolver.process_heading("E. Processing Specifications")
    resolver.process_heading("1. Modules")
    assert resolver.process_heading("4. Reports - Audit and Provenance Logs") == "E. Processing Specifications - 4. Reports - Audit and Provenance Logs"
    # When updated subtopic arrives under same number 4, update title in place
    assert resolver.process_heading("4. Reports - Operational and Compliance Reports") == "E. Processing Specifications - 4. Reports - Operational and Compliance Reports"
    # Unnumbered subtopic update under same base
    assert resolver.process_heading("Operational and Compliance Reports") == "E. Processing Specifications - 4. Reports - Operational and Compliance Reports"


def test_hierarchy_resolver_rejects_regressive_root_under_appendices():
    """Verify that earlier root sections like D are never nested as children of K. Appendices."""
    resolver = HeaderHierarchyResolver()
    resolver.process_heading("K. Appendices")
    assert resolver.get_current_breadcrumb() == "K. Appendices"

    # Out-of-order / stale heading from Section D must NOT become child of K. Appendices
    assert resolver.is_stale_heading("D. Technology Stack Requirements") is True
    res = resolver.process_heading("D. Technology Stack Requirements")
    assert res == "K. Appendices"
    assert "D. Technology Stack" not in resolver.get_current_breadcrumb()
    assert len(resolver.stack) == 1


def test_merge_chunks_longest_common_prefix():
    """Verify that merging chunks under the same subsection preserves longest common breadcrumb prefix."""
    c1 = EvaluationChunk(
        chunk_id="c1",
        heading="E. Processing Specifications - 4. Reports - Audit and Provenance Logs",
        page_range=(9, 10),
        structured_text="Audit logs text",
        element_refs=[],
        figures=[],
    )
    c2 = EvaluationChunk(
        chunk_id="c2",
        heading="E. Processing Specifications - 4. Reports - Operational and Compliance Reports",
        page_range=(10, 11),
        structured_text="Operational reports text",
        element_refs=[],
        figures=[],
    )
    merged = merge_chunks([c1, c2], max_chars=1000)
    assert len(merged) == 1
    assert merged[0].heading == "E. Processing Specifications - 4. Reports"
    assert merged[0].page_range == (9, 11)


def test_build_document_index_reading_order_preserves_section_sequence():
    """Verify that build_document_index sorts items into physical reading order so Section D is not under K. Appendices."""
    from cheshire_configs.preprocessors.multistep.helpers.indexing import build_document_index
    from types import SimpleNamespace

    mock_page = SimpleNamespace(size=SimpleNamespace(height=1000.0, width=800.0))
    pages = {5: mock_page, 6: mock_page, 17: mock_page}

    class MockItem:
        def __init__(self, self_ref, label, text, page_no, top_y):
            self.self_ref = self_ref
            self.label = label
            self.text = text
            self.prov = [SimpleNamespace(page_no=page_no, bbox=BoundingBox(l=50.0, t=top_y, r=500.0, b=top_y + 20.0, coord_origin=CoordOrigin.TOPLEFT))]

    # Out-of-order items: K. Appendices (p17), then D. Tech Stack (p5), then E. Processing (p6)
    items_out_of_order = [
        MockItem("#/texts/k", "section_header", "K. Appendices", page_no=17, top_y=100.0),
        MockItem("#/texts/d", "section_header", "D. Technology Stack Requirements", page_no=5, top_y=200.0),
        MockItem("#/texts/e", "section_header", "E. Processing Specifications", page_no=6, top_y=100.0),
    ]

    mock_doc = SimpleNamespace(
        iterate_items=lambda **kwargs: [(it, 0) for it in items_out_of_order],
        pages=pages,
        pictures=[],
        texts=[],
        tables=[],
    )

    idx = build_document_index(mock_doc)
    sec_titles = [s["title"] for s in idx["sections"]]
    assert sec_titles == ["D. Technology Stack Requirements", "E. Processing Specifications", "K. Appendices"]
    assert idx["sections"][0]["page"] == 5
    assert idx["sections"][1]["page"] == 6
    assert idx["sections"][2]["page"] == 17


def test_build_document_index_table_banner_title_update():
    """Verify that an unnumbered table banner row updates the section title in place."""
    from cheshire_configs.preprocessors.multistep.helpers.indexing import build_document_index
    from types import SimpleNamespace

    mock_page = SimpleNamespace(size=SimpleNamespace(height=1000.0, width=800.0))
    pages = {9: mock_page, 10: mock_page}

    class MockCell:
        def __init__(self, text):
            self.text = text

    items = [
        SimpleNamespace(
            self_ref="#/texts/1",
            label="section_header",
            text="E. Processing Specifications",
            prov=[SimpleNamespace(page_no=9, bbox=BoundingBox(l=50, t=30, r=500, b=50, coord_origin=CoordOrigin.TOPLEFT))],
        ),
        SimpleNamespace(
            self_ref="#/texts/1b",
            label="section_header",
            text="1. Modules",
            prov=[SimpleNamespace(page_no=9, bbox=BoundingBox(l=50, t=55, r=500, b=70, coord_origin=CoordOrigin.TOPLEFT))],
        ),
        SimpleNamespace(
            self_ref="#/texts/2",
            label="section_header",
            text="4. Reports - Audit and Provenance Logs",
            prov=[SimpleNamespace(page_no=9, bbox=BoundingBox(l=50, t=80, r=500, b=100, coord_origin=CoordOrigin.TOPLEFT))],
        ),
        # Table 1 under Audit and Provenance Logs
        SimpleNamespace(
            self_ref="#/tables/1",
            label="table",
            data=SimpleNamespace(grid=[
                [MockCell("Log Name"), MockCell("Description")],
                [MockCell("Audit Trail"), MockCell("Cryptographic trail")],
            ]),
            prov=[SimpleNamespace(page_no=9, bbox=BoundingBox(l=50, t=120, r=500, b=250, coord_origin=CoordOrigin.TOPLEFT))],
        ),
        # Table 2 on page 10 with banner header "Operational and Compliance Reports"
        SimpleNamespace(
            self_ref="#/tables/2",
            label="table",
            data=SimpleNamespace(grid=[
                [MockCell("Operational and Compliance Reports"), MockCell("")],
                [MockCell("Report"), MockCell("Description")],
                [MockCell("Statutory Burn-Rate"), MockCell("Burn rate measurement")],
            ]),
            prov=[SimpleNamespace(page_no=10, bbox=BoundingBox(l=50, t=50, r=500, b=200, coord_origin=CoordOrigin.TOPLEFT))],
        ),
    ]

    mock_doc = SimpleNamespace(
        iterate_items=lambda **kwargs: [(it, 0) for it in items],
        pages=pages,
        pictures=[],
        texts=[],
        tables=[],
    )

    idx = build_document_index(mock_doc)
    assert len(idx["tables"]) == 2
    assert idx["tables"][0]["section"] == "E. Processing Specifications - 4. Reports - Audit and Provenance Logs"
    assert idx["tables"][1]["section"] == "E. Processing Specifications - 4. Reports - Operational and Compliance Reports"


def test_build_document_index_e2_diagrams_and_e3_files_records_separation():
    """Verify that E.2 Diagrams and E.3 Files and Records are correctly separated."""
    from cheshire_configs.preprocessors.multistep.helpers.indexing import build_document_index
    from types import SimpleNamespace

    mock_page = SimpleNamespace(size=SimpleNamespace(height=1000.0, width=800.0))
    pages = {5: mock_page, 6: mock_page}

    class MockCell:
        def __init__(self, text):
            self.text = text

    items = [
        SimpleNamespace(
            self_ref="#/texts/e",
            label="section_header",
            text="E. Processing Specifications",
            prov=[SimpleNamespace(page_no=5, bbox=BoundingBox(l=50, t=50, r=500, b=70, coord_origin=CoordOrigin.TOPLEFT))],
        ),
        SimpleNamespace(
            self_ref="#/texts/mod_h",
            label="section_header",
            text="1. Modules",
            prov=[SimpleNamespace(page_no=5, bbox=BoundingBox(l=50, t=75, r=500, b=90, coord_origin=CoordOrigin.TOPLEFT))],
        ),
        SimpleNamespace(
            self_ref="#/texts/diag_h",
            label="section_header",
            text="2. Diagrams",
            prov=[SimpleNamespace(page_no=5, bbox=BoundingBox(l=50, t=100, r=500, b=120, coord_origin=CoordOrigin.TOPLEFT))],
        ),
        SimpleNamespace(
            self_ref="#/tables/diag_tbl",
            label="table",
            data=SimpleNamespace(grid=[
                [MockCell("Diagram"), MockCell("Attachment")],
                [MockCell("Network Diagram"), MockCell("Network.pdf")],
                [MockCell("Process Flow Diagram"), MockCell("PFD.pdf")],
            ]),
            prov=[SimpleNamespace(page_no=5, bbox=BoundingBox(l=50, t=130, r=500, b=250, coord_origin=CoordOrigin.TOPLEFT))],
        ),
        SimpleNamespace(
            self_ref="#/texts/files_h",
            label="section_header",
            text="3. Files and Records",
            prov=[SimpleNamespace(page_no=6, bbox=BoundingBox(l=50, t=50, r=500, b=70, coord_origin=CoordOrigin.TOPLEFT))],
        ),
        SimpleNamespace(
            self_ref="#/tables/11",
            label="table",
            data=SimpleNamespace(grid=[
                [MockCell("Files"), MockCell("Description")],
                [MockCell("ISAD Schema Definition"), MockCell("Core payload schema")],
            ]),
            prov=[SimpleNamespace(page_no=6, bbox=BoundingBox(l=50, t=80, r=500, b=250, coord_origin=CoordOrigin.TOPLEFT))],
        ),
    ]

    mock_doc = SimpleNamespace(
        iterate_items=lambda **kwargs: [(it, 0) for it in items],
        pages=pages,
        pictures=[],
        texts=[],
        tables=[],
    )

    idx = build_document_index(mock_doc)
    assert len(idx["tables"]) == 2
    # Table diag_tbl belongs to E.2 Diagrams
    assert "2. Diagrams" in idx["tables"][0]["section"]
    # Table 11 belongs to E.3 Files and Records, NOT 2. Diagrams
    assert "3. Files and Records" in idx["tables"][1]["section"]
    assert "2. Diagrams" not in idx["tables"][1]["section"]


def test_full_architecture_specifications_progression():
    """
    Verify complete architectural progression:
    - Section D is root at page 5 (before E and before K)
    - E.2 Diagrams contains diagram table and harvests diagram_documents
    - E.3 Files & Records contains Table 11
    - Table banner updates Section 4 to Operational and Compliance Reports
    - F. System Considerations and G. Security Considerations close Section E
    - K. Appendices is root at page 17
    """
    from cheshire_configs.preprocessors.multistep.helpers.indexing import build_document_index
    from types import SimpleNamespace

    mock_page = SimpleNamespace(size=SimpleNamespace(height=1000.0, width=800.0))
    pages = {p: mock_page for p in (5, 6, 8, 10, 12, 14, 15, 17)}

    class MockCell:
        def __init__(self, text):
            self.text = text

    items = [
        # Page 5: Section D
        SimpleNamespace(
            self_ref="#/texts/d",
            label="section_header",
            text="D. Technology Stack Requirements",
            prov=[SimpleNamespace(page_no=5, bbox=BoundingBox(l=50, t=50, r=500, b=70, coord_origin=CoordOrigin.TOPLEFT))],
        ),
        SimpleNamespace(
            self_ref="#/tables/d_tbl",
            label="table",
            data=SimpleNamespace(grid=[
                [MockCell("Component"), MockCell("Technology"), MockCell("Version")],
                [MockCell("Message Queue"), MockCell("RabbitMQ"), MockCell("3.12")],
            ]),
            prov=[SimpleNamespace(page_no=5, bbox=BoundingBox(l=50, t=80, r=500, b=200, coord_origin=CoordOrigin.TOPLEFT))],
        ),
        # Page 5: Section E
        SimpleNamespace(
            self_ref="#/texts/e",
            label="section_header",
            text="E. Processing Specifications",
            prov=[SimpleNamespace(page_no=5, bbox=BoundingBox(l=50, t=250, r=500, b=270, coord_origin=CoordOrigin.TOPLEFT))],
        ),
        SimpleNamespace(
            self_ref="#/texts/e1",
            label="section_header",
            text="1. Modules",
            prov=[SimpleNamespace(page_no=5, bbox=BoundingBox(l=50, t=280, r=500, b=300, coord_origin=CoordOrigin.TOPLEFT))],
        ),
        SimpleNamespace(
            self_ref="#/texts/e2",
            label="section_header",
            text="2. Diagrams",
            prov=[SimpleNamespace(page_no=5, bbox=BoundingBox(l=50, t=310, r=500, b=330, coord_origin=CoordOrigin.TOPLEFT))],
        ),
        SimpleNamespace(
            self_ref="#/tables/diag_tbl",
            label="table",
            data=SimpleNamespace(grid=[
                [MockCell("Diagram"), MockCell("Attachment")],
                [MockCell("Network Diagram"), MockCell("Network.pdf")],
                [MockCell("Process Flow Diagram - Serialization"), MockCell("PFD.pdf")],
                [MockCell("Sequence Diagram - Serialization"), MockCell("Seq.pdf")],
                [MockCell("Data Flow Diagram"), MockCell("DFD.pdf")],
            ]),
            prov=[SimpleNamespace(page_no=5, bbox=BoundingBox(l=50, t=340, r=500, b=500, coord_origin=CoordOrigin.TOPLEFT))],
        ),
        # Page 6: Section E.3
        SimpleNamespace(
            self_ref="#/texts/e3",
            label="section_header",
            text="3. Files and Records",
            prov=[SimpleNamespace(page_no=6, bbox=BoundingBox(l=50, t=50, r=500, b=70, coord_origin=CoordOrigin.TOPLEFT))],
        ),
        SimpleNamespace(
            self_ref="#/tables/tbl11",
            label="table",
            data=SimpleNamespace(grid=[
                [MockCell("Files"), MockCell("Description")],
                [MockCell("ISAD Schema Definition"), MockCell("Schema spec")],
            ]),
            prov=[SimpleNamespace(page_no=6, bbox=BoundingBox(l=50, t=80, r=500, b=250, coord_origin=CoordOrigin.TOPLEFT))],
        ),
        # Page 8: Section E.4
        SimpleNamespace(
            self_ref="#/texts/e4",
            label="section_header",
            text="4. Reports - Audit and Provenance Logs",
            prov=[SimpleNamespace(page_no=8, bbox=BoundingBox(l=50, t=50, r=500, b=70, coord_origin=CoordOrigin.TOPLEFT))],
        ),
        # Page 10: Table with unnumbered banner
        SimpleNamespace(
            self_ref="#/tables/reports_banner",
            label="table",
            data=SimpleNamespace(grid=[
                [MockCell("Operational and Compliance Reports"), MockCell(""), MockCell("")],
                [MockCell("Report"), MockCell("Description"), MockCell("Class")],
                [MockCell("Statutory Burn-Rate"), MockCell("Burn rate report"), MockCell("ReportClient.cs")],
            ]),
            prov=[SimpleNamespace(page_no=10, bbox=BoundingBox(l=50, t=50, r=500, b=300, coord_origin=CoordOrigin.TOPLEFT))],
        ),
        # Page 12: Section E.5
        SimpleNamespace(
            self_ref="#/texts/e5",
            label="section_header",
            text="5. Parameter and Lookup Files",
            prov=[SimpleNamespace(page_no=12, bbox=BoundingBox(l=50, t=50, r=500, b=70, coord_origin=CoordOrigin.TOPLEFT))],
        ),
        # Page 14: Section F
        SimpleNamespace(
            self_ref="#/texts/f",
            label="section_header",
            text="F. System Considerations",
            prov=[SimpleNamespace(page_no=14, bbox=BoundingBox(l=50, t=50, r=500, b=70, coord_origin=CoordOrigin.TOPLEFT))],
        ),
        # Page 15: Section G
        SimpleNamespace(
            self_ref="#/texts/g",
            label="section_header",
            text="G. Security Considerations",
            prov=[SimpleNamespace(page_no=15, bbox=BoundingBox(l=50, t=50, r=500, b=70, coord_origin=CoordOrigin.TOPLEFT))],
        ),
        # Page 17: Section K
        SimpleNamespace(
            self_ref="#/texts/k",
            label="section_header",
            text="K. Appendices",
            prov=[SimpleNamespace(page_no=17, bbox=BoundingBox(l=50, t=50, r=500, b=70, coord_origin=CoordOrigin.TOPLEFT))],
        ),
    ]

    mock_doc = SimpleNamespace(
        iterate_items=lambda **kwargs: [(it, 0) for it in items],
        pages=pages,
        pictures=[],
        texts=[],
        tables=[],
    )

    idx = build_document_index(mock_doc)

    # 1. Section D is root and appears before Section E and K
    sec_titles = [s["title"] for s in idx["sections"]]
    assert "D. Technology Stack Requirements" in sec_titles
    d_sec = next(s for s in idx["sections"] if "Technology Stack" in s["title"])
    assert d_sec["root_section"] == "D. Technology Stack Requirements"
    assert "Appendices" not in d_sec["root_section"]
    assert "Appendices" not in d_sec["title"]
    assert d_sec["page"] == 5

    # 2. Diagrams harvested
    diag_names = [d["name"] for d in idx["diagram_documents"]]
    assert any("Network Diagram" in n for n in diag_names)
    assert any("Process Flow" in n for n in diag_names)
    assert any("Sequence Diagram" in n for n in diag_names)
    assert any("Data Flow Diagram" in n for n in diag_names)

    # 3. Table 11 belongs to 3. Files and Records
    tbl11_entry = next(t for t in idx["tables"] if t["id"] == "#/tables/tbl11")
    assert "3. Files and Records" in tbl11_entry["section"]
    assert "2. Diagrams" not in tbl11_entry["section"]

    # 4. Reports banner update
    rep_tbl = next(t for t in idx["tables"] if t["id"] == "#/tables/reports_banner")
    assert "Operational and Compliance Reports" in rep_tbl["section"]

    # 5. Section F and G are root sections, not under Files and Records
    f_sec = next(s for s in idx["sections"] if "System Considerations" in s["title"])
    assert f_sec["root_section"] == "F. System Considerations"
    assert "Files and Records" not in f_sec["title"]

    g_sec = next(s for s in idx["sections"] if "Security Considerations" in s["title"])
    assert g_sec["root_section"] == "G. Security Considerations"
    assert "Files and Records" not in g_sec["title"]

    k_sec = next(s for s in idx["sections"] if "Appendices" in s["title"])
    assert k_sec["root_section"] == "K. Appendices"
    assert "Technology Stack" not in k_sec["title"]


def test_table_header_row_not_section_header_and_full_document_indexing():
    """
    Verify that table column headers like '(N)ew / (E)xisting Description Attachment Attachment Class/Module'
    are rejected from section extraction, and do not pollute sections F, G, H, I, J, K or diagram_documents.
    """
    from cheshire_configs.preprocessors.multistep.helpers.hierarchy import _extract_heading_from_text, parse_header_token
    from cheshire_configs.preprocessors.multistep.helpers.indexing import build_document_index
    from types import SimpleNamespace

    # 1. Direct text extractor check
    table_header_line = "(N)ew / (E)xisting Description Attachment Attachment Class/Module"
    assert _extract_heading_from_text(table_header_line) is None
    assert parse_header_token(table_header_line).is_unnumbered is True

    # 2. Document index test
    mock_page = SimpleNamespace(size=SimpleNamespace(height=1000.0, width=800.0))
    pages = {p: mock_page for p in (5, 6, 8, 11, 15, 16, 17)}

    class MockCell:
        def __init__(self, text):
            self.text = text

    items = [
        SimpleNamespace(self_ref="#/texts/e", label="section_header", text="E. Processing Specifications", prov=[SimpleNamespace(page_no=5, bbox=BoundingBox(l=50, t=30, r=500, b=50, coord_origin=CoordOrigin.TOPLEFT))]),
        SimpleNamespace(self_ref="#/texts/e1", label="section_header", text="1. Modules", prov=[SimpleNamespace(page_no=5, bbox=BoundingBox(l=50, t=60, r=500, b=80, coord_origin=CoordOrigin.TOPLEFT))]),
        SimpleNamespace(self_ref="#/texts/e2", label="section_header", text="2. Diagrams", prov=[SimpleNamespace(page_no=6, bbox=BoundingBox(l=50, t=30, r=500, b=50, coord_origin=CoordOrigin.TOPLEFT))]),
        SimpleNamespace(
            self_ref="#/tables/diag_tbl",
            label="table",
            data=SimpleNamespace(grid=[
                [MockCell("Diagram"), MockCell("Attachment")],
                [MockCell("Network Diagram"), MockCell("AWV Compliant Reporting Service Network Diagram.pdf")],
                [MockCell("Process Flow Diagram – Serialization and Reporting Service"), MockCell("PID-0015 Serialization and Reporting Process Flow Diagram.pdf")],
                [MockCell("Sequence Diagram – Serialization and Reporting Service"), MockCell("PID-0015 Serialization and Reporting Sequence Diagram.pdf")],
                [MockCell("Data Flow Diagram"), MockCell("PID-0015 Serialization and Reporting Data Flow Diagram.pdf")],
            ]),
            prov=[SimpleNamespace(page_no=6, bbox=BoundingBox(l=50, t=60, r=500, b=250, coord_origin=CoordOrigin.TOPLEFT))],
        ),
        SimpleNamespace(self_ref="#/texts/e3", label="section_header", text="3. Files and Records", prov=[SimpleNamespace(page_no=6, bbox=BoundingBox(l=50, t=260, r=500, b=280, coord_origin=CoordOrigin.TOPLEFT))]),
        SimpleNamespace(self_ref="#/texts/tbl_hdr", label="paragraph", text=table_header_line, prov=[SimpleNamespace(page_no=6, bbox=BoundingBox(l=50, t=290, r=500, b=310, coord_origin=CoordOrigin.TOPLEFT))]),
        SimpleNamespace(self_ref="#/texts/e4", label="section_header", text="4. Reports", prov=[SimpleNamespace(page_no=8, bbox=BoundingBox(l=50, t=30, r=500, b=50, coord_origin=CoordOrigin.TOPLEFT))]),
        SimpleNamespace(self_ref="#/texts/e5", label="section_header", text="5. Parameter and Lookup Files", prov=[SimpleNamespace(page_no=11, bbox=BoundingBox(l=50, t=30, r=500, b=50, coord_origin=CoordOrigin.TOPLEFT))]),
        SimpleNamespace(
            self_ref="#/tables/param_tbl",
            label="table",
            data=SimpleNamespace(grid=[
                [MockCell("Parameters")],
                [MockCell("File Name"), MockCell("(N)ew / (E)xisting"), MockCell("Description")],
                [MockCell("AppSettings.json"), MockCell("E"), MockCell("App settings configuration")],
                [MockCell("ACK_MANIFEST_EOD.xml"), MockCell("E"), MockCell("FinCEN cryptographic dispatch manifest")],
            ]),
            prov=[SimpleNamespace(page_no=11, bbox=BoundingBox(l=50, t=60, r=500, b=200, coord_origin=CoordOrigin.TOPLEFT))],
        ),
        SimpleNamespace(self_ref="#/texts/f", label="paragraph", text="F. System Considerations", prov=[SimpleNamespace(page_no=15, bbox=BoundingBox(l=50, t=30, r=500, b=50, coord_origin=CoordOrigin.TOPLEFT))]),
        SimpleNamespace(self_ref="#/texts/g", label="paragraph", text="G. Security Considerations", prov=[SimpleNamespace(page_no=15, bbox=BoundingBox(l=50, t=200, r=500, b=220, coord_origin=CoordOrigin.TOPLEFT))]),
        SimpleNamespace(self_ref="#/texts/h", label="paragraph", text="H. Estimates", prov=[SimpleNamespace(page_no=16, bbox=BoundingBox(l=50, t=30, r=500, b=50, coord_origin=CoordOrigin.TOPLEFT))]),
        SimpleNamespace(self_ref="#/texts/i", label="paragraph", text="I. Attachments", prov=[SimpleNamespace(page_no=17, bbox=BoundingBox(l=50, t=30, r=500, b=50, coord_origin=CoordOrigin.TOPLEFT))]),
        SimpleNamespace(self_ref="#/texts/j", label="paragraph", text="J. Sonar Scan Result", prov=[SimpleNamespace(page_no=17, bbox=BoundingBox(l=50, t=100, r=500, b=120, coord_origin=CoordOrigin.TOPLEFT))]),
        SimpleNamespace(self_ref="#/texts/k", label="paragraph", text="K. Appendices", prov=[SimpleNamespace(page_no=17, bbox=BoundingBox(l=50, t=200, r=500, b=220, coord_origin=CoordOrigin.TOPLEFT))]),
    ]

    mock_doc = SimpleNamespace(
        iterate_items=lambda **kwargs: [(it, 0) for it in items],
        pages=pages,
        pictures=[],
        texts=[it for it in items if it.label != "table"],
        tables=[it for it in items if it.label == "table"],
    )

    idx = build_document_index(mock_doc)

    # Table header string MUST NOT be in sections
    assert not any("(N)ew" in s["title"] for s in idx["sections"])

    # Sections F, G, H, I, J, K must all be present as distinct root sections
    sec_titles = [s["title"] for s in idx["sections"]]
    assert any("F. System Considerations" in t for t in sec_titles)
    assert any("G. Security Considerations" in t for t in sec_titles)
    assert any("H. Estimates" in t for t in sec_titles)
    assert any("I. Attachments" in t for t in sec_titles)
    assert any("J. Sonar Scan Result" in t for t in sec_titles)
    assert any("K. Appendices" in t for t in sec_titles)

    # Section I. Attachments must be its own root section (not subordinate to H. Estimates)
    i_sec = next(s for s in idx["sections"] if "I. Attachments" in s["title"])
    assert i_sec["root_section"] == "I. Attachments"
    assert "H. Estimates" not in i_sec["root_section"]

    # Parameter table must not pollute diagram_documents
    diag_names = [d["name"] for d in idx["diagram_documents"]]
    assert "Network Diagram" in diag_names
    assert "Process Flow Diagram – Serialization and Reporting Service" in diag_names
    assert "Sequence Diagram – Serialization and Reporting Service" in diag_names
    assert "Data Flow Diagram" in diag_names
    assert "AppSettings.json" not in diag_names
    assert "ACK_MANIFEST_EOD.xml" not in diag_names


def test_letter_ordering_progression_h_i_j_k():
    """Verify that letter progression H -> I -> J -> K correctly treats I as letter 9."""
    from cheshire_configs.preprocessors.multistep.helpers.hierarchy import HeaderHierarchyResolver

    resolver = HeaderHierarchyResolver()
    assert resolver.process_heading("H. Estimates") == "H. Estimates"
    assert resolver.get_root_key() == "H"

    assert not resolver.is_stale_heading("I. Attachments")
    assert resolver.process_heading("I. Attachments") == "I. Attachments"
    assert resolver.get_root_key() == "I"

    assert not resolver.is_stale_heading("J. Sonar Scan Result")
    assert resolver.process_heading("J. Sonar Scan Result") == "J. Sonar Scan Result"
    assert resolver.get_root_key() == "J"

    assert not resolver.is_stale_heading("K. Appendices")
    assert resolver.process_heading("K. Appendices") == "K. Appendices"
    assert resolver.get_root_key() == "K"


def test_cover_page_preamble_replaced_by_first_numbered_section():
    """Verify that unnumbered preamble/cover metadata does not trap the document."""
    from cheshire_configs.preprocessors.multistep.helpers.hierarchy import HeaderHierarchyResolver, _is_spurious_heading

    # Tracking information must be rejected as spurious cover metadata
    assert _is_spurious_heading("TRACKING INFORMATION")

    resolver = HeaderHierarchyResolver()
    # Preamble unnumbered header
    assert resolver.process_heading("Executive Summary") == "Executive Summary"
    assert resolver.get_root_heading() == "Executive Summary"

    # Numbered section A. Overview must replace the unnumbered preamble
    assert not resolver.is_stale_heading("A. Overview")
    assert resolver.process_heading("A. Overview") == "A. Overview"
    assert resolver.get_root_heading() == "A. Overview"
    assert resolver.get_root_key() == "A"

    assert resolver.process_heading("B. Reference Documents") == "B. Reference Documents"
    assert resolver.get_root_key() == "B"


def test_multi_letter_acronyms_and_filenames_rejected():
    """Verify that acronyms like DLQ/PID and filenames are rejected as headings."""
    from cheshire_configs.preprocessors.multistep.helpers.hierarchy import (
        HeaderHierarchyResolver,
        _extract_heading_from_text,
        parse_header_token,
    )

    non_headings = [
        "(DLQ) and Exception",
        "PID-0010 AWV Compliant Reporting Service",
        "PID-0015 AWV Serialization and Reporting of Rule 17-B ISAD",
        "ID10-AWV.pdf",
        "filing_ledger.sql",
        "outbox_schema.sql",
        "AppSettings.json",
        "way_specs.yaml",
        "Write-Once-Read-Many",
        "Burn-Rate Report",
        "End-of-Day (EOD)",
        "7-year statutory retention in",
        "\\\\crestview-internal\\Auditing_Section\\AWV",
        "C:/Downloads",
    ]

    for item in non_headings:
        cand = _extract_heading_from_text(item)
        assert cand is None, f"Expected {item!r} to be rejected by _extract_heading_from_text, got {cand!r}"

    # Also verify that if fed to HeaderHierarchyResolver, unnumbered tokens never jump sequence
    resolver = HeaderHierarchyResolver()
    resolver.process_heading("E. Processing Specifications")
    for item in non_headings:
        tok = parse_header_token(item)
        assert tok.is_unnumbered or not tok.segments or tok.segments[0].val == 0


def test_zero_width_and_invisible_characters_in_outline_headings():
    """Verify that zero-width spaces (\u200b, \ufeff) and control chars in headings are stripped and resolved."""
    from cheshire_configs.preprocessors.multistep.helpers.hierarchy import (
        HeaderHierarchyResolver,
        _extract_heading_from_text,
        _normalize_heading_text,
        parse_header_token,
    )

    headings = [
        "\u200bA. Overview:",
        "\u200bC. Technical Specifications",
        "\u200bD. Technology Stack Requirements",
        "\u200bE. Processing Specifications",
        "1.\u200bModules (programs, executable scripts, etc.)",
        "2.\u200bDiagrams",
        "3.\u200bFiles and Records",
        "4.\u200bReports",
        "5.\u200bParameter and Lookup Files",
        "6.\u200bOthers",
        "\u200bF. System Considerations",
        "\u200bG. Security Considerations",
        "\u200bI. Attachments",
        "\u200bJ. Sonar Scan Result:",
        "\u200bK. Appendices",
    ]

    resolver = HeaderHierarchyResolver()
    resolved_paths = []
    for h in headings:
        cand = _extract_heading_from_text(h)
        assert cand is not None, f"Failed to extract heading from {h!r}"
        assert not resolver.is_stale_heading(cand)
        res = resolver.process_heading(cand)
        resolved_paths.append(res)

    assert "A. Overview" in resolved_paths[0]
    assert "D. Technology Stack Requirements" in resolved_paths[2]
    assert resolved_paths[2] == "D. Technology Stack Requirements"
    assert resolved_paths[4] == "E. Processing Specifications - 1. Modules (programs, executable scripts, etc.)"
    assert resolved_paths[5] == "E. Processing Specifications - 2. Diagrams"
    assert resolved_paths[6] == "E. Processing Specifications - 3. Files and Records"
    assert resolved_paths[10] == "F. System Considerations"
    assert resolved_paths[11] == "G. Security Considerations"
    assert resolved_paths[14] == "K. Appendices"


def test_multi_line_paragraph_with_intro_colon_extracts_heading():
    """Verify that multi-line paragraph items with intro narrative ending in colon extract the outline heading."""
    from cheshire_configs.preprocessors.multistep.helpers.hierarchy import _extract_heading_from_text

    block1 = (
        "The purpose of this section is to detail any changes or modifications required for each of the following:\n"
        "1. Modules (programs, executable scripts, etc.)"
    )
    cand1 = _extract_heading_from_text(block1)
    assert cand1 == "1. Modules (programs, executable scripts, etc.)"

    block2 = (
        "3. Files and Records\n"
        "Files\n"
        "(N)ew /\n"
        "(E)xisting\n"
        "Description Attachment\n"
        "Class/Module"
    )
    cand2 = _extract_heading_from_text(block2)
    assert cand2 == "3. Files and Records"

    pure_table_header = (
        "Files\n"
        "(N)ew /\n"
        "(E)xisting\n"
        "Description Attachment\n"
        "Class/Module"
    )
    assert _extract_heading_from_text(pure_table_header) is None


def test_end_to_end_goldstandard_tds_structure():
    """
    Comprehensive simulation matching goldstandard_sampletds.pdf structure:
    - Section C (p3)
    - Section D Tech Stack (p4) correctly binds the figure to Section D, not C
    - Section E Processing (p5-14) with 1. Modules, 2. Diagrams, 3. Files and Records, 4. Reports, 5. Parameters, 6. Others
    - Diagram table on p6 populates diagram_documents and figure captions
    - Section F System Considerations and Section G Security Considerations on p15-16
    - Section D is never nested under Section K Appendices
    - Zero figures leak into TRACKING INFORMATION
    """
    from cheshire_configs.preprocessors.multistep.helpers.indexing import build_document_index
    from cheshire_configs.preprocessors.multistep.helpers.chunking import _extract_section_key, _propagate_section_figures
    from cheshire_configs.preprocessors.multistep.helpers.models import EvaluationChunk, FigureRef
    from types import SimpleNamespace

    mock_page = SimpleNamespace(size=SimpleNamespace(height=1000.0, width=800.0))
    pages = {p: mock_page for p in range(1, 19)}

    class MockCell:
        def __init__(self, text):
            self.text = text

    items = [
        # p1: Cover page / Tracking
        SimpleNamespace(
            self_ref="#/texts/track",
            label="section_header",
            text="TRACKING INFORMATION - PID-0010 AWV Compliant Reporting Service",
            prov=[SimpleNamespace(page_no=1, bbox=BoundingBox(l=50, t=50, r=500, b=70, coord_origin=CoordOrigin.TOPLEFT))],
        ),
        # p2: Section B Reference Documents
        SimpleNamespace(
            self_ref="#/texts/b",
            label="section_header",
            text="B. Reference Documents",
            prov=[SimpleNamespace(page_no=2, bbox=BoundingBox(l=50, t=50, r=500, b=70, coord_origin=CoordOrigin.TOPLEFT))],
        ),
        # p3: Section C Technical Specifications
        SimpleNamespace(
            self_ref="#/texts/c",
            label="section_header",
            text="C. Technical Specifications",
            prov=[SimpleNamespace(page_no=3, bbox=BoundingBox(l=50, t=50, r=500, b=70, coord_origin=CoordOrigin.TOPLEFT))],
        ),
        # p4: Section D Tech Stack (frame begins at t=55, text begins at t=75)
        SimpleNamespace(
            self_ref="#/pictures/d_frame",
            label="picture",
            caption_text=lambda doc=None: None,
            text="",
            prov=[SimpleNamespace(page_no=4, bbox=BoundingBox(l=40, t=55, r=760, b=750, coord_origin=CoordOrigin.TOPLEFT))],
        ),
        SimpleNamespace(
            self_ref="#/texts/d_head",
            label="section_header",
            text="D Technology Stack Requirements",
            prov=[SimpleNamespace(page_no=4, bbox=BoundingBox(l=50, t=75, r=500, b=95, coord_origin=CoordOrigin.TOPLEFT))],
        ),
        # p5: Section E Processing Specifications & 1. Modules
        SimpleNamespace(
            self_ref="#/texts/e_head",
            label="section_header",
            text="E. Processing Specifications",
            prov=[SimpleNamespace(page_no=5, bbox=BoundingBox(l=50, t=50, r=500, b=70, coord_origin=CoordOrigin.TOPLEFT))],
        ),
        SimpleNamespace(
            self_ref="#/texts/e_lead",
            label="paragraph",
            text="The purpose of this section is to detail any changes or modifications required for each of the following:\n1. Modules (programs, executable scripts, etc.)",
            prov=[SimpleNamespace(page_no=5, bbox=BoundingBox(l=50, t=80, r=500, b=120, coord_origin=CoordOrigin.TOPLEFT))],
        ),
        # p6: 2. Diagrams with Diagram Table and icon pictures
        SimpleNamespace(
            self_ref="#/texts/e2_diag",
            label="section_header",
            text="2. Diagrams",
            prov=[SimpleNamespace(page_no=6, bbox=BoundingBox(l=50, t=50, r=500, b=70, coord_origin=CoordOrigin.TOPLEFT))],
        ),
        SimpleNamespace(
            self_ref="#/tables/diag_tbl",
            label="table",
            data=SimpleNamespace(grid=[
                [MockCell("Diagram"), MockCell("Attachment")],
                [MockCell("Network Diagram"), MockCell("AWV Compliant Reporting Service Network Diagram.pdf")],
                [MockCell("Process Flow Diagram – Serialization and Reporting Service"), MockCell("PID-0015 Serialization and Reporting Process Flow Diagram.pdf")],
                [MockCell("Sequence Diagram – Serialization and Reporting Service"), MockCell("PID-0015 Serialization and Reporting Sequence Diagram.pdf")],
                [MockCell("Data Flow Diagram"), MockCell("PID-0015 Serialization and Reporting Data Flow Diagram.pdf")],
            ]),
            prov=[SimpleNamespace(page_no=6, bbox=BoundingBox(l=50, t=80, r=500, b=280, coord_origin=CoordOrigin.TOPLEFT))],
        ),
        SimpleNamespace(
            self_ref="#/pictures/icon_net",
            label="picture",
            caption_text=lambda doc=None: None,
            text="",
            prov=[SimpleNamespace(page_no=6, bbox=BoundingBox(l=400, t=110, r=450, b=150, coord_origin=CoordOrigin.TOPLEFT))],
        ),
        SimpleNamespace(
            self_ref="#/pictures/icon_pfd",
            label="picture",
            caption_text=lambda doc=None: None,
            text="",
            prov=[SimpleNamespace(page_no=6, bbox=BoundingBox(l=400, t=160, r=450, b=200, coord_origin=CoordOrigin.TOPLEFT))],
        ),
        # p6: 3. Files and Records
        SimpleNamespace(
            self_ref="#/texts/e3_files",
            label="section_header",
            text="3. Files and Records",
            prov=[SimpleNamespace(page_no=6, bbox=BoundingBox(l=50, t=320, r=500, b=340, coord_origin=CoordOrigin.TOPLEFT))],
        ),
        SimpleNamespace(
            self_ref="#/tables/files_tbl",
            label="table",
            data=SimpleNamespace(grid=[
                [MockCell("Files"), MockCell("(N)ew / (E)xisting"), MockCell("Description"), MockCell("Attachment"), MockCell("Class/Module")],
                [MockCell("ISAD Schema Definition"), MockCell("N"), MockCell("Version 1.0"), MockCell("IsadSchema.pdf"), MockCell("IsadSchema.cs")],
            ]),
            prov=[SimpleNamespace(page_no=6, bbox=BoundingBox(l=50, t=350, r=500, b=550, coord_origin=CoordOrigin.TOPLEFT))],
        ),
        # p15: Section F System Considerations and Section G Security Considerations
        SimpleNamespace(
            self_ref="#/texts/f_head",
            label="section_header",
            text="F. System Considerations",
            prov=[SimpleNamespace(page_no=15, bbox=BoundingBox(l=50, t=50, r=500, b=70, coord_origin=CoordOrigin.TOPLEFT))],
        ),
        SimpleNamespace(
            self_ref="#/texts/g_head",
            label="section_header",
            text="G. Security Considerations",
            prov=[SimpleNamespace(page_no=15, bbox=BoundingBox(l=50, t=350, r=500, b=370, coord_origin=CoordOrigin.TOPLEFT))],
        ),
        # p17: Section K Appendices
        SimpleNamespace(
            self_ref="#/texts/k_head",
            label="section_header",
            text="K. Appendices",
            prov=[SimpleNamespace(page_no=17, bbox=BoundingBox(l=50, t=100, r=500, b=120, coord_origin=CoordOrigin.TOPLEFT))],
        ),
    ]

    mock_doc = SimpleNamespace(
        iterate_items=lambda **kwargs: [(it, 0) for it in items],
        pages=pages,
        pictures=[it for it in items if it.label == "picture"],
        texts=[it for it in items if it.label in ("section_header", "paragraph")],
        tables=[it for it in items if it.label == "table"],
    )

    idx = build_document_index(mock_doc)

    sec_titles = [s["title"] for s in idx["sections"]]
    assert any("Technology Stack Requirements" in s for s in sec_titles)
    assert "E. Processing Specifications" in sec_titles
    assert "E. Processing Specifications - 1. Modules (programs, executable scripts, etc.)" in sec_titles
    assert "E. Processing Specifications - 2. Diagrams" in sec_titles
    assert "E. Processing Specifications - 3. Files and Records" in sec_titles
    assert "F. System Considerations" in sec_titles
    assert "G. Security Considerations" in sec_titles
    assert "K. Appendices" in sec_titles

    # Verify Section D is NOT under K. Appendices
    d_sec = next(s for s in idx["sections"] if "Technology Stack Requirements" in s["title"])
    assert "Technology Stack Requirements" in d_sec["root_section"]

    # Verify picture on p4 is filed under Section D, NOT Section C
    d_fig = next(f for f in idx["figures"] if f["id"] == "#/pictures/d_frame")
    assert "Technology Stack Requirements" in d_fig["section"]

    # Verify diagram_documents populated
    assert len(idx["diagram_documents"]) >= 4
    diag_names = [d["name"] for d in idx["diagram_documents"]]
    assert any("Network Diagram" in n for n in diag_names)
    assert any("Process Flow Diagram" in n for n in diag_names)
    assert any("Sequence Diagram" in n for n in diag_names)
    assert any("Data Flow Diagram" in n for n in diag_names)

    # Verify diagram icon pictures on p6 received diagram captions
    p6_figs = [f for f in idx["figures"] if f["id"] in ("#/pictures/icon_net", "#/pictures/icon_pfd")]
    assert all(f.get("caption") for f in p6_figs)

    from cheshire_configs.preprocessors.multistep.helpers.models import EvaluationChunk, FigureRef, ImageBoundingBox
    dummy_img = ImageBoundingBox(x1=0, y1=0, x2=10, y2=10)
    dummy_pdf = BoundingBox(l=0, t=0, r=10, b=10, coord_origin=CoordOrigin.TOPLEFT)

    # Verify figure propagation excludes TRACKING INFORMATION
    chunk_preamble = EvaluationChunk(
        chunk_id="c0",
        heading="TRACKING INFORMATION - PID-0010 AWV Compliant Reporting Service",
        page_range=(1, 2),
        structured_text="Preamble",
        figures=[],
    )
    chunk_d = EvaluationChunk(
        chunk_id="c1",
        heading="D. Technology Stack Requirements",
        page_range=(4, 4),
        structured_text="Tech Stack",
        figures=[FigureRef(figure_id="fig_d", page_number=4, base64_png="data:image/png;base64,abc", bbox_image_px=dummy_img, bbox_pdf=dummy_pdf)],
    )
    chunk_e = EvaluationChunk(
        chunk_id="c2",
        heading="E. Processing Specifications - 2. Diagrams",
        page_range=(6, 6),
        structured_text="Diagrams",
        figures=[FigureRef(figure_id="fig_diag", page_number=6, base64_png="data:image/png;base64,xyz", bbox_image_px=dummy_img, bbox_pdf=dummy_pdf)],
    )
    test_chunks = [chunk_preamble, chunk_d, chunk_e]
    _propagate_section_figures(test_chunks)
    assert len(chunk_preamble.figures) == 0  # No figures leaked into tracking preamble!










