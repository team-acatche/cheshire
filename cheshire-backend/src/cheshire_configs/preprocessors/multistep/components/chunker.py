from haystack import component
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
from docling_core.types.doc import DoclingDocument
from docling.datamodel.document import ConversionResult
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.chunking import HierarchicalChunker
from docling_core.transforms.chunker.hierarchical_chunker import ChunkingSerializerProvider, ChunkingDocSerializer
from docling_core.transforms.serializer.markdown import MarkdownParams
from cheshire_configs.preprocessors.multistep.helpers import EvaluationChunk, build_chunks, build_document_index


class ImagePlaceholderSerializerProvider(ChunkingSerializerProvider):
    def get_serializer(self, doc) -> ChunkingDocSerializer:
        return ChunkingDocSerializer(
            doc=doc,
            params=MarkdownParams(
                image_placeholder="[## IMAGE ##]"
            )
        )


@component
class MultistepDoclingConverter:
    """
    Wraps Docling's DocumentConverter and HierarchicalChunker.
    Accepts a PDF path, returns structured chunks and a document index.
    """

    def __init__(self, images_scale: float = 2.0):
        pipeline_options: PdfPipelineOptions = PdfPipelineOptions()
        pipeline_options.images_scale = images_scale
        pipeline_options.generate_picture_images = True

        self._converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=pipeline_options
                )
            }
        )
        self._chunker = HierarchicalChunker(
            serializer_provider=ImagePlaceholderSerializerProvider()
        )

    @component.output_types(
        chunks=list, 
        document_index=dict
    )
    def run(self, pdf_path: str) -> dict:
        result: ConversionResult = self._converter.convert(pdf_path)
        doc: DoclingDocument = result.document

        chunks: list[EvaluationChunk] = build_chunks(doc, result, self._chunker)
        document_index: dict = build_document_index(doc)

        return {
            "chunks": chunks,
            "document_index": document_index
        }