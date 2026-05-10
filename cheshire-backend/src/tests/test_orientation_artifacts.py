import pytest
from haystack import Document
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel
from docling_core.types.doc.document import PictureMeta, DescriptionMetaField
from docling_core.transforms.chunker import DocChunk # type: ignore

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
    doc_title = Document(content="title chunk", meta={
        "dl_meta": {
            "text": "The Title",
            "meta": {
                "doc_items": [{
                    "self_ref": "#/texts/0",
                    "label": "title",
                    "prov": [{
                        "page_no": 1,
                        "bbox": {"l": 0, "t": 0, "r": 0, "b": 0},
                        "charspan": [0, 9]
                    }]
                }]
            }
        }
    })
    doc_pic = Document(content="picture chunk", meta={
        "dl_meta": {
            "text": "A picture description",
            "meta": {
                "doc_items": [{
                    "self_ref": "#/pictures/0",
                    "label": "picture",
                    "prov": [{
                        "page_no": 1,
                        "bbox": {"l": 0, "t": 0, "r": 0, "b": 0},
                        "charspan": [0, 21]
                    }],
                    "meta": {
                        "img__description": {"text": "A picture description"}
                    }
                }]
            }
        }
    })
    
    result = extractor.run(documents=[doc_title, doc_pic])
    output_docs = result["documents"]
    
    # 2 original chunks + skeleton + visual index = 4 documents
    assert len(output_docs) == 4
    
    types = [d.meta.get("type", "chunk") for d in output_docs]
    assert "orientation_skeleton" in types
    assert "orientation_visual_index" in types


def test_orientation_extractor_with_raw_items():
    extractor = DoclingOrientationExtractor()

    # Create separate documents to ensure all items are processed (extractor logic is one type per chunk)
    doc_title = Document(content="chunk", meta={"dl_meta": {
        "text": "The Title",
        "meta": {"doc_items": [{
            "self_ref": "#/texts/0", "label": "title", "prov": [{"page_no": 1, "bbox": {"l": 0, "t": 0, "r": 0, "b": 0}, "charspan": [0, 9]}]
        }]}
    }})
    doc_header = Document(content="chunk", meta={"dl_meta": {
        "text": "The Header",
        "meta": {"doc_items": [{
            "self_ref": "#/texts/1", "label": "section_header", "prov": [{"page_no": 1, "bbox": {"l": 0, "t": 0, "r": 0, "b": 0}, "charspan": [0, 10]}]
        }]}
    }})
    doc_text = Document(content="chunk", meta={"dl_meta": {
        "text": "Some text content here...",
        "meta": {"doc_items": [{
            "self_ref": "#/texts/2", "label": "text", "prov": [{"page_no": 1, "bbox": {"l": 0, "t": 0, "r": 0, "b": 0}, "charspan": [0, 25]}]
        }]}
    }})
    doc_pic = Document(content="chunk", meta={"dl_meta": {
        "text": "A picture description",
        "meta": {"doc_items": [{
            "self_ref": "#/pictures/0", "label": "picture", "prov": [{"page_no": 2, "bbox": {"l": 0, "t": 0, "r": 0, "b": 0}, "charspan": [0, 21]}],
            "meta": {"img__description": {"text": "A picture description"}}
        }]}
    }})
    
    result = extractor.run(documents=[doc_title, doc_header, doc_text, doc_pic])
    output_docs = result["documents"]
    
    skeleton_doc = next(d for d in output_docs if d.meta.get("type") == "orientation_skeleton")
    visual_index_doc = next(d for d in output_docs if d.meta.get("type") == "orientation_visual_index")
    
    skeleton_content = skeleton_doc.content
    assert "Title: The Title" in skeleton_content
    # The current extractor doesn't add [H2] prefix, it just adds the text for headers found in chunk labels
    assert "[Header] The Header" in skeleton_content 
    assert "Some text content here" in skeleton_content

    visual_index_content = visual_index_doc.content
    assert "[Visual/Table on page 2: A picture description]" in visual_index_content
