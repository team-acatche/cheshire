from document_source import DocumentSource
from docling_core.types.doc import DoclingDocument
from docling_core.types.doc.document import PictureMeta, DescriptionMetaField
from docling_core.types.doc.labels import DocItemLabel


def _make_doc_with_text() -> DoclingDocument:
    """Create a DoclingDocument with a couple of text items."""
    doc = DoclingDocument(name="test-doc")
    doc.add_text(label=DocItemLabel.PARAGRAPH, text="Hello world.")
    doc.add_text(label=DocItemLabel.PARAGRAPH, text="Second paragraph.")
    return doc


def _make_doc_with_picture(description: str | None = None) -> DoclingDocument:
    """Create a DoclingDocument with a picture that has a caption and optional description."""
    doc = DoclingDocument(name="picture-doc")
    # First create the caption TextItem, then pass it to add_picture
    caption_item = doc.add_text(label=DocItemLabel.CAPTION, text="A nice photo")
    pic = doc.add_picture(caption=caption_item)
    if description:
        pic.meta = PictureMeta(description=DescriptionMetaField(text=description))
    return doc


def test_from_docling_text_items():
    doc = _make_doc_with_text()
    sources = DocumentSource.from_docling_document(doc)

    assert len(sources) == 2
    assert sources[0].text == "Hello world."
    assert sources[1].text == "Second paragraph."

    for src in sources:
        assert src.source_id  # non-empty uuid
        assert src.metadata.document_id == "test-doc"
        assert src.metadata.summary == ""


def test_from_docling_empty_document():
    doc = DoclingDocument(name="empty-doc")
    sources = DocumentSource.from_docling_document(doc)
    assert sources == []


def test_from_docling_picture_caption():
    doc = _make_doc_with_picture()
    sources = DocumentSource.from_docling_document(doc)

    # Should pick up the picture via its caption
    picture_sources = [s for s in sources if "photo" in s.text]
    assert len(picture_sources) >= 1
    assert "A nice photo" in picture_sources[0].text


def test_from_docling_picture_with_description():
    doc = _make_doc_with_picture(description="Landscape at sunset")
    sources = DocumentSource.from_docling_document(doc)

    picture_sources = [s for s in sources if "sunset" in s.text]
    assert len(picture_sources) == 1
    # Both caption and description should be present
    assert "A nice photo" in picture_sources[0].text
    assert "Landscape at sunset" in picture_sources[0].text
