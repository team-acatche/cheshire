from haystack import component
from haystack.dataclasses import ChatMessage, ImageContent, TextContent
from cheshire_configs.preprocessors.multistep.helpers import EvaluationChunk, FigureRef
import json


@component
class ChunkMessageBuilder:
    """
    Builds a multimodal ChatMessage for one chunk.
    Text elements carry their [ID:...] annotations.
    Figure crops are embedded as base64 image_url parts.
    """

    @component.output_types(messages=list[ChatMessage])
    def run(
        self,
        chunk: EvaluationChunk,
        document_index: dict,
        previous_findings: list | None = None
    ) -> dict:

        prompt_text: str = f"Document index:\n{json.dumps(document_index, indent=2)}"
        
        if previous_findings:
            prompt_text += f"\n\nFindings identified in previous sections:\n{json.dumps(previous_findings, indent=2)}"
            
        # Section structure context for lead-in awareness
        import re
        curr_key = None
        m = re.match(r'^([A-Z]|\d+)\b(?:\.|\s|$)', chunk.heading.strip())
        if m:
            curr_key = m.group(1)
        elif chunk.heading.startswith("Section "):
            m2 = re.match(r'^Section\s+([A-Z]|\d+)\b', chunk.heading.strip())
            if m2:
                curr_key = m2.group(1)

        section_context_note = ""
        if curr_key and document_index and "sections" in document_index:
            related = [
                s["title"] for s in document_index["sections"]
                if re.match(rf'^{curr_key}(?:\.|\s|$)', s.get("title", "").strip())
            ]
            if len(related) > 1:
                section_context_note = (
                    f"\n\n[Section Structure Context: This section is part of Section {curr_key}, which contains: "
                    f"{', '.join(related)}. "
                    f"Introductory or lead-in framing paragraphs here introduce those subsections.]"
                )

        prompt_text += (
            f"\n\n--- Section: {chunk.heading} "
            f"(pages {chunk.page_range[0]}-{chunk.page_range[1]}) ---"
            f"{section_context_note}"
            f"\n\n{chunk.structured_text}"
        )

        content: list[TextContent | ImageContent] = [
            TextContent(prompt_text)
        ]

        for fig in chunk.figures:
            fig: FigureRef
            content.append(TextContent(f"\n[Figure ID:{fig.figure_id} | page {fig.page_number}]"))
            content.append(ImageContent(fig.base64_png, "image/png"))

        return {"messages": [ChatMessage.from_user(content_parts=content)]}