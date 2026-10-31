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

    # section d and section e remain separate chunks with correct page bounds
    assert len(merged) == 2
    assert merged[0].heading == "D. Technology Stack Requirements"
    assert merged[0].page_range == (5, 6)
    assert merged[1].heading == "E. Processing Specifications"
    assert merged[1].page_range == (7, 13)


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

