from docling.chunking import HierarchicalChunker
from docling_core.transforms.chunker.hierarchical_chunker import ChunkingDocSerializer
from docling_core.types.doc import DoclingDocument

from cheshire_configs.preprocessors.multistep.components.chunker import (
    ImagePlaceholderSerializerProvider,
    MultistepDoclingConverter,
)


def test_image_placeholder_serializer_provider():
    """Verify that ImagePlaceholderSerializerProvider configures image_placeholder to '[## IMAGE ##]'."""
    provider = ImagePlaceholderSerializerProvider()
    doc = DoclingDocument(name="test_doc")
    serializer = provider.get_serializer(doc)

    assert isinstance(serializer, ChunkingDocSerializer)
    assert serializer.params.image_placeholder == "[## IMAGE ##]"


def test_chunker_substitutes_image_placeholder():
    """Verify that HierarchicalChunker with ImagePlaceholderSerializerProvider outputs '[## IMAGE ##]' for pictures."""
    doc = DoclingDocument(name="test_doc")
    doc.add_text(text="Paragraph before image", label="paragraph")
    doc.add_picture()
    doc.add_text(text="Paragraph after image", label="paragraph")

    chunker = HierarchicalChunker(serializer_provider=ImagePlaceholderSerializerProvider())
    chunks = list(chunker.chunk(doc))

    # Should produce chunks for text and picture items
    assert len(chunks) == 3
    assert chunks[0].text == "Paragraph before image"
    assert chunks[1].text == "[## IMAGE ##]"
    assert chunks[2].text == "Paragraph after image"
    assert chunker.contextualize(chunks[1]) == "[## IMAGE ##]"


def test_multistep_docling_converter_initializes_placeholder_serializer():
    """Verify that MultistepDoclingConverter configures its chunker with ImagePlaceholderSerializerProvider."""
    converter = MultistepDoclingConverter()
    assert isinstance(converter._chunker.serializer_provider, ImagePlaceholderSerializerProvider)

    # Verify that the converter's chunker also substitutes image placeholders
    doc = DoclingDocument(name="test_doc")
    doc.add_text(text="Introductory text", label="paragraph")
    doc.add_picture()

    chunks = list(converter._chunker.chunk(doc))
    assert any(c.text == "[## IMAGE ##]" for c in chunks)
