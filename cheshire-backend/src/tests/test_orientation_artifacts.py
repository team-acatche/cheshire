import pytest
from haystack import Document
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel
from docling_core.types.doc.document import PictureMeta, DescriptionMetaField
from docling.chunking import DocChunk

from cheshire_configs.preprocessors.rag import DoclingOrientationExtractor


def _make_sample_docling_document() -> DoclingDocument:
    doc = DoclingDocument(name="sample-doc")
    # Add title
    doc.add_text(label=DocItemLabel.TITLE, text="Main Research Paper")
    # Add section header
    doc.add_text(label=DocItemLabel.SECTION_HEADER, text="Introduction")
    # Add some text
    doc.add_text(label=DocItemLabel.PARAGRAPH, text="This is the introduction text.")

    # Add second section header with level 2
    item = doc.add_text(label=DocItemLabel.SECTION_HEADER, text="Background")

    # Add a picture with description
    caption_item = doc.add_text(label=DocItemLabel.CAPTION, text="A sample figure")
    pic = doc.add_picture(caption=caption_item)
    pic.meta = PictureMeta(description=DescriptionMetaField(text="This diagram shows the system architecture."))

    return doc

def test_orientation_extractor_existence():
    """Verify that skeleton and visual_index are added as standalone documents."""
    extractor = DoclingOrientationExtractor()
    doc_meta = {
        "dl_meta": {
            "meta": {
                "doc_items": [
                    {
                        "label": "title",
                        "text": "The Title",
                        "prov": [{"page_no": 1}]
                    },
                    {
                        "label": "picture",
                        "prov": [{"page_no": 1}],
                        "meta": {
                            "description": {
                                "text": "A picture description"
                            }
                        }
                    }
                ]
            }
        }
    }
    doc = Document(content="chunk", meta=doc_meta)
    
    result = extractor.run(documents=[doc])
    output_docs = result["documents"]
    
    # original chunk + skeleton + visual index = 3 documents
    assert len(output_docs) == 3
    
    types = [d.meta.get("type", "chunk") for d in output_docs]
    assert "orientation_skeleton" in types
    assert "orientation_visual_index" in types


def test_orientation_extractor_with_raw_items():
    extractor = DoclingOrientationExtractor()

    # Create a mock internal structure for DocChunk
    doc_meta = {
        "dl_meta": {
            "meta": {
                "doc_items": [
                    {
                        "label": "title",
                        "text": "The Title",
                        "prov": [{"page_no": 1}]
                    },
                    {
                        "label": "section_header",
                        "text": "The Header",
                        "level": 2,
                        "prov": [{"page_no": 1}]
                    },
                    {
                        "label": "text",
                        "text": "Some text content here...",
                        "prov": [{"page_no": 1}]
                    },
                    {
                        "label": "picture",
                        "prov": [{"page_no": 2}],
                        "meta": {
                            "description": {
                                "text": "A picture description"
                            }
                        }
                    }
                ]
            }
        }
    }
    
    doc = Document(content="chunk", meta=doc_meta)
    
    result = extractor.run(documents=[doc])
    output_docs = result["documents"]
    
    skeleton_doc = next(d for d in output_docs if d.meta.get("type") == "orientation_skeleton")
    visual_index_doc = next(d for d in output_docs if d.meta.get("type") == "orientation_visual_index")
    
    skeleton_content = skeleton_doc.content
    assert "Title: The Title" in skeleton_content
    assert "\t[H2] The Header" in skeleton_content
    assert "Some text content here" in skeleton_content

    visual_index_content = visual_index_doc.content
    assert "picture on page 2: A picture description" in visual_index_content
