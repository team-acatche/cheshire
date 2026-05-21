import json
from haystack import component
from haystack.dataclasses import ChatMessage

PASS2_SYSTEM_PROMPT = """\
You are a technical reviewer synthesising a multi-section document audit.

INPUT  Raw findings JSON array and document index.

TASKS
  1. Deduplicate findings describing the same issue across sections.
  2. Identify cross-section contradictions.
  3. Rank all findings: critical > high > medium > low > observation.
  4. Flag findings with confidence < 0.75 for human review.
  5. Tally findings per standard_ref.

OUTPUT  Return only a JSON object:
  findings            array   Deduplicated, ranked; preserve all original fields
  contradictions      array   [{section_a, section_b, description}]
  compliance_summary  object  {standard_id: count}
  human_review_flags  array   [element_id, ...]\
"""


@component
class SynthesisMessageBuilder:
    """
    Builds the two-message conversation for Pass 2:
    a system message carrying the task definition, and a user message
    carrying the findings payload and document index.

    Keeping the system prompt here rather than in the generator constructor
    mirrors the pattern used in Pass 1 and means all prompt logic lives
    in message builder components, not scattered across pipeline config.
    """

    @component.output_types(messages=list)  # List[ChatMessage]
    def run(
        self,
        all_findings: list,
        document_index: dict
    ) -> dict:
        messages = [
            ChatMessage.from_system(PASS2_SYSTEM_PROMPT),
            ChatMessage.from_user(
                f"Document index:\n{json.dumps(document_index, indent=2)}"
                f"\n\nAll findings:\n{json.dumps(all_findings, indent=2)}"
            )
        ]
        return {"messages": messages}