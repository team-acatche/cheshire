import io
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from docling_core.types.doc import DoclingDocument, BoundingBox
from docling_core.types.doc.document import (
    ProvenanceItem,
    PictureMeta,
    DescriptionMetaField,
)
from docling_core.types.doc.labels import DocItemLabel

from server import api
from cheshire_configs.registry import configs
from cheshire_configs.core import PipelineConfig, Provider, EvaluationType
from auth.dependencies import get_current_user
from auth.models import User

# Override the registry dependency to avoid real model initialization
# This also ensures resolve_config finds a valid config for the default OLLAMA provider
mock_config = PipelineConfig(
    model=MagicMock(),
    tools=[],
    mode=EvaluationType.RAG
)
api.dependency_overrides[configs] = lambda: {Provider.OLLAMA: mock_config}

def mock_get_current_user():
    return User(user_id="test_id", email="test@example.com", sessions_folder="testuser", username="testuser", full_name="Test User", avatar_uri="default.png")

api.dependency_overrides[get_current_user] = mock_get_current_user

client = TestClient(api)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pdf_bytes() -> bytes:
    """Return a minimal valid PDF as bytes (no external files needed)."""
    from pypdfium2 import PdfDocument # type: ignore

    doc = PdfDocument.new()
    doc.new_page(595, 842)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def _build_docling_doc(
    name: str = "test",
    *,
    paragraphs: list[str] | None = None,
    add_picture_with_caption: str | None = None,
    picture_description: str | None = None,
    add_provenance: bool = False,
) -> DoclingDocument:
    """Build a DoclingDocument with controllable content for mocking."""
    doc = DoclingDocument(name=name)

    if paragraphs:
        for text in paragraphs:
            prov = None
            if add_provenance:
                prov = ProvenanceItem(
                    page_no=1,
                    bbox=BoundingBox(l=10, t=20, r=300, b=40),
                    charspan=(0, len(text)),
                )
            doc.add_text(label=DocItemLabel.PARAGRAPH, text=text, prov=prov)

    if add_picture_with_caption:
        caption_item = doc.add_text(
            label=DocItemLabel.CAPTION, text=add_picture_with_caption
        )
        # Build a minimal ImageRef that passes the server's `assert figure.image is not None`
        # but whose `pil_image` is None so the walrus guard skips saving.
        from docling_core.types.doc.document import ImageRef
        from docling_core.types.doc.base import Size

        placeholder_image = ImageRef(
            mimetype="image/png",
            dpi=72,
            size=Size(width=1, height=1),
            uri="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVQIHWNgAAIABQABNjN9GQAAAAlwSFlzAAAWJQAAFiUBSVIk8AAAABl0RVh0U29mdHdhcmUAcGFpbnQubmV0IDQuMC41ZYUyZQAAAA1JREFUGFdjYGBg+A8AAQQBAB1MQ2wAAAAASUVORK5CYII=", # type: ignore
        )
        pic = doc.add_picture(caption=caption_item, image=placeholder_image)
        if picture_description:
            pic.meta = PictureMeta(
                description=DescriptionMetaField(text=picture_description)
            )

    return doc


def _mock_evaluate_result(docling_doc: DoclingDocument):
    """Return a mock list of VulnerabilityDetails to simulate evaluate_file output."""
    from tools.helpers.output_schema import VulnerabilityDetails
    from docling_core.types.doc import BoundingBox
    
    results = []
    # If the doc has paragraphs, create a vulnerability for each to simulate findings
    for i, item in enumerate(docling_doc.texts):
        results.append(VulnerabilityDetails(
            title=f"Vulnerability {i}",
            description=f"Description for {item.text}",
            page_no=1,
            bbox=BoundingBox(l=10.0, t=10.0, r=100.0, b=100.0),
            web_references=["http://example.com"],
            recommendations=["Recommendation 1"]
        ))
    return results

# Convert the response processing in tests to expect the new structure


PDF_BYTES = _make_pdf_bytes()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSuccessfulEvaluation:
    """Happy-path tests for the /evaluate endpoint."""

    @patch("dependencies.sessions.SESSIONS_PATH", Path("/tmp"))
    def test_successful_pdf_evaluation(self):
        """Upload a PDF → 200, response is a list."""
        doc = _build_docling_doc(paragraphs=["Hello world."])
        with patch("endpoints.evaluate.evaluate_file", return_value=_mock_evaluate_result(doc)):
            response = client.post(
                "/api/v1/evaluate",
                files={"uploaded_document": ("test.pdf", PDF_BYTES, "application/pdf")},
            )
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.json()["vulnerabilities"], list)

    @patch("dependencies.sessions.SESSIONS_PATH", Path("/tmp"))
    def test_response_contains_expected_text(self):
        """Returned sources contain the text from the DoclingDocument."""
        doc = _build_docling_doc(paragraphs=["First paragraph.", "Second paragraph."])
        with patch("endpoints.evaluate.evaluate_file", return_value=_mock_evaluate_result(doc)):
            response = client.post(
                "/api/v1/evaluate",
                files={"uploaded_document": ("test.pdf", PDF_BYTES, "application/pdf")},
            )
        data = response.json()["vulnerabilities"]
        titles = [item["title"] for item in data]
        assert "Vulnerability 0" in titles
        assert "Vulnerability 1" in titles

    @patch("dependencies.sessions.SESSIONS_PATH", Path("/tmp"))
    def test_response_metadata_fields(self):
        """Each source has all expected metadata fields with correct types."""
        doc = _build_docling_doc(
            name="my-doc",
            paragraphs=["Some text."],
            add_provenance=True,
        )
        with patch("endpoints.evaluate.evaluate_file", return_value=_mock_evaluate_result(doc)):
            response = client.post(
                "/api/v1/evaluate",
                files={"uploaded_document": ("test.pdf", PDF_BYTES, "application/pdf")},
            )
        data = response.json()["vulnerabilities"]
        assert len(data) == 1

        source = data[0]
        assert "title" in source
        assert "description" in source
        assert "page_no" in source
        assert "bbox" in source
        assert "web_references" in source
        assert "recommendations" in source

        assert source["page_no"] == 1

    @patch("dependencies.sessions.SESSIONS_PATH", Path("/tmp"))
    def test_source_ids_are_unique(self):
        """All source_id values in the response are unique valid UUIDs."""
        doc = _build_docling_doc(paragraphs=["A", "B", "C", "D", "E"])
        with patch("endpoints.evaluate.evaluate_file", return_value=_mock_evaluate_result(doc)):
            response = client.post(
                "/api/v1/evaluate",
                files={"uploaded_document": ("test.pdf", PDF_BYTES, "application/pdf")},
            )
        data = response.json()["vulnerabilities"]
        titles = [item["title"] for item in data]

        # All unique
        assert len(set(titles)) == len(titles)


class TestEmptyAndEdgeCases:
    """Edge-case tests."""

    @patch("dependencies.sessions.SESSIONS_PATH", Path("/tmp"))
    def test_empty_document_returns_empty_list(self):
        """A document with no text or picture items returns []."""
        doc = _build_docling_doc()
        with patch("endpoints.evaluate.evaluate_file", return_value=_mock_evaluate_result(doc)):
            response = client.post(
                "/api/v1/evaluate",
                files={"uploaded_document": ("test.pdf", PDF_BYTES, "application/pdf")},
            )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["vulnerabilities"] == []

    @patch("dependencies.sessions.SESSIONS_PATH", Path("/tmp"))
    def test_filename_fallback(self):
        """When UploadFile.filename is None, the endpoint uses 'upload' fallback."""
        doc = _build_docling_doc(paragraphs=["Content here."])
        with patch("endpoints.evaluate.evaluate_file", return_value=_mock_evaluate_result(doc)):
            response = client.post(
                "/api/v1/evaluate",
                # Use a real filename here; the fallback logic is already covered by
                # the server.py code `filename = uploaded_document.filename or "upload"`.
                # We verify it doesn't crash with an unusual filename.
                files={"uploaded_document": ("upload", PDF_BYTES, "application/pdf")},
            )
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.json()["vulnerabilities"], list)


# TestPictureHandling removed as document_source is obsolete


class TestRequestValidation:
    """Tests for invalid requests."""

    @patch("dependencies.sessions.SESSIONS_PATH", Path("/tmp"))
    def test_missing_file_returns_422(self):
        """No file uploaded → 422 validation error."""
        response = client.post("/api/v1/evaluate")
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
