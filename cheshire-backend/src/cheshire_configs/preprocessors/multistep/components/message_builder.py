from haystack import component
from haystack.dataclasses import ChatMessage, ImageContent, TextContent
from cheshire_configs.preprocessors.multistep.helpers import EvaluationChunk
import json


@component
class ChunkMessageBuilder:
    """
    Builds a multimodal ChatMessage for one chunk.
    Text elements carry their [ID:...] annotations.
    Figure crops are embedded as base64 image_url parts.
    """

    @component.output_types(messages=list) # List[ChatMessage]
    def run(
        self,
        chunk: EvaluationChunk,
        document_index: dict,
        previous_findings: list | None = None
    ) -> dict:

        prompt_text = f"Document index:\n{json.dumps(document_index, indent=2)}"
        
        if previous_findings:
            prompt_text += f"\n\nFindings identified in previous sections:\n{json.dumps(previous_findings, indent=2)}"
            
        prompt_text += (
            f"\n\n--- Section: {chunk.heading} "
            f"(pages {chunk.page_range[0]}-{chunk.page_range[1]}) ---"
            f"\n\n{chunk.structured_text}"
        )

        content: list[TextContent | ImageContent] = [
            TextContent(prompt_text)
        ]

        for fig in chunk.figures:
            content.append(TextContent(f"\n[Figure ID:{fig.figure_id} | page {fig.page_number}]"))
            content.append(ImageContent(fig.base64_png, "image/png"))

        return {"messages": [ChatMessage.from_user(content_parts=content)]}