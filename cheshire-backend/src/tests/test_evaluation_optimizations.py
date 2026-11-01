import json
from unittest.mock import MagicMock
from docling_core.types.doc import BoundingBox

from cheshire_configs.preprocessors.multistep.components.message_builder import ChunkMessageBuilder
from cheshire_configs.preprocessors.multistep.helpers import (
    EvaluationChunk,
    FigureRef,
    LocalFinding,
    DEFAULT_MAX_CHUNK_CHARS,
    DEFAULT_IMAGE_SCALE,
)
from cheshire_configs.preprocessors.multistep.helpers.chunking import merge_chunks
from cheshire_configs.preprocessors.multistep.tools import inspect_figure, batch_accept_findings


def test_constants_optimized():
    # test scale and chunk limits
    assert DEFAULT_IMAGE_SCALE == 1.0
    assert DEFAULT_MAX_CHUNK_CHARS == 6000


def test_message_builder_prunes_table_rows():
    # test table rows pruned from prompt
    builder = ChunkMessageBuilder()
    chunk = EvaluationChunk(
        chunk_id="c0",
        heading="Overview",
        page_range=(1, 1),
        structured_text="[ID:p1|paragraph|p1] Hello world",
    )
    doc_index = {
        "sections": [{"title": "Overview", "page": 1}],
        "tables": [
            {
                "id": "#/tables/0",
                "page": 2,
                "section": "Reports",
                "headers": ["Report", "Status"],
                "rows": ["Report A | Pass", "Report B | Fail"],
            }
        ],
    }

    res = builder.run(chunk=chunk, document_index=doc_index)
    msg_text = res["messages"][0].text

    assert "Document index:" in msg_text
    assert '"headers":["Report","Status"]' in msg_text or '"headers": ["Report", "Status"]' in msg_text
    # rows should not be in the serialized prompt
    assert '"rows"' not in msg_text
    assert "Report A | Pass" not in msg_text


def test_message_builder_omits_previous_findings():
    # test previous findings not in prompt
    builder = ChunkMessageBuilder()
    chunk = EvaluationChunk(
        chunk_id="c1",
        heading="Security",
        page_range=(2, 2),
        structured_text="[ID:p2|paragraph|p2] Content",
    )
    doc_index = {"sections": []}
    prev_findings = [{"finding": "Old finding", "severity": "major"}]

    res = builder.run(chunk=chunk, document_index=doc_index, previous_findings=prev_findings)
    msg_text = res["messages"][0].text

    assert "Findings identified in previous sections" not in msg_text
    assert "Old finding" not in msg_text


def test_inspect_figure():
    # test inspect figure tool
    fig = FigureRef(
        figure_id="#/pictures/0",
        page_number=4,
        bbox_image_px=[0, 0, 10, 10],
        bbox_pdf=BoundingBox(l=0, t=10, r=10, b=0),
        base64_png="data",
    )
    chunk = EvaluationChunk(
        chunk_id="c0",
        heading="Architecture",
        page_range=(4, 4),
        structured_text="text",
        figures=[fig],
    )

    res_id = inspect_figure.invoke(query="#/pictures/0", chunks_cache=[chunk])
    assert "[Figure ID:#/pictures/0 | page 4]" in res_id

    res_page = inspect_figure.invoke(query="page 4", chunks_cache=[chunk])
    assert "[Figure ID:#/pictures/0 | page 4]" in res_page

    res_none = inspect_figure.invoke(query="nonexistent", chunks_cache=[chunk])
    assert "Warning: No figure found" in res_none


def test_merge_chunks_continuation():
    # test merge continuation chunks up to max_chars
    c1 = EvaluationChunk(
        chunk_id="c0",
        heading="E. Processing Specifications - 1. Modules",
        page_range=(1, 1),
        structured_text="Module specs 1",
    )
    c2 = EvaluationChunk(
        chunk_id="c1",
        heading="E. Processing Specifications - 1. Modules",
        page_range=(2, 2),
        structured_text="Module specs 2",
    )

    merged = merge_chunks([c1, c2], max_chars=6000)
    assert len(merged) == 1
    assert "Module specs 1" in merged[0].structured_text
    assert "Module specs 2" in merged[0].structured_text
    assert merged[0].page_range == (1, 2)

