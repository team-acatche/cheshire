from enum import StrEnum, auto
from dataclasses import dataclass, field, replace
from typing import Protocol, runtime_checkable, Optional, Callable
from pathlib import Path
from haystack.core.pipeline import Pipeline
from haystack.document_stores.types import DocumentStore
from haystack.components.generators.chat.llm import ChatGenerator, ChatMessage
from haystack.components.embedders.types import TextEmbedder, DocumentEmbedder
from haystack.tools import ToolsType

from tools.base import add_vulnerability_tool, read_vulnerabilities_tool, finish as finish_tool
from tools.exa import web_search

class EvaluationType(StrEnum):
    MULTISTEP = auto()

class Provider(StrEnum):
    OPENROUTER = auto()

@runtime_checkable
class DocumentPreprocessor(Protocol):
    def __call__(self, document: Path, store: DocumentStore | None = None) -> None:
        ...

@runtime_checkable
class ToolFactory(Protocol):
    @property
    def tools(self) -> ToolsType:
        ...
    
    def extend(self, factory: "ToolFactory"):
        ...

@dataclass
class DefaultToolFactory(ToolFactory):
    extra_tools: list = field(default_factory=list, init=False)

    @property
    def tools(self) -> ToolsType:
        return [
            web_search,
            add_vulnerability_tool("vulnerabilities_list"),
            read_vulnerabilities_tool("vulnerabilities_list"),
            finish_tool,
        ] + self.extra_tools
    
    def extend(self, factory: ToolFactory):
        self.extra_tools.extend(factory.tools)

@dataclass(frozen=True)
class PipelineConfig:
    model: ChatGenerator
    tools: ToolsType = field(default_factory=list)
    mode: EvaluationType = EvaluationType.MULTISTEP
    document_store: Optional[DocumentStore] = None
    preprocessor: Optional[DocumentPreprocessor] = None
    document_embedder: Optional[Callable[[], DocumentEmbedder]] = None
    embedder: Optional[Callable[[], TextEmbedder]] = None
    system_prompt: str = """
        You are an expert security and technical design auditor performing a preemptive review before the document is handed over to the Information Security department, to lessen further walkthrough and revision cycles.

        ## Core Mandate & Guiding Questions
        Your ultimate goal is to determine if the document contains adequate, correct information to start development, specifically focusing on:
        1. "Is the technical design secure enough to produce a secure-by-design program once deployed?"
        2. "Is the technical design specifications enough to initiate development?"
        You have been given the `web_search` tool to use the internet as a knowledge base to ensure both questions are answered thoroughly.
        The findings should help the author achieve higher document quality and a more secure technical design. Provide quality recommendations and verifiable references.

        ## Categories of Discrepancies
        Record discrepancies across four categories:
        a) Company standards
        b) Security standards and risk
        c) Writing quality
        d) Content correctness and appropriateness

        ## Situational Standards & Sensible Decisions
        Standards are situational. Determine applicability by referencing each standard against the document's content (e.g., specifications for internal tooling do not need a Third-Party Contract, empty table cells can be a sensible alternative for emptiness like N/A, and technology-specific standards only apply when those technologies are used, such as TDE for Azure SQL). Make justifiable and sensible decisions on which rules to apply and which to ignore based on context.

        ## Severity Tiers
        - "major": Findings that will most likely halt approval from the Information Security Department and should be resolved before approval.
        - "minor": Findings that will most likely hinder development, but might still be approved; should be resolved before development.
        - "observation": Findings that will not affect approval nor development, but will help improve the quality of the document.

        ## Figures and Attachments Policy
        Figures or content referenced as file attachments or external links are assumed to be perfectly compliant; do not open said attachments or links. Otherwise, scrutinize figures in the document itself across quality, correctness, and drafting norms.

        ## Process
        You MUST execute the following iterative process until you have fully analyzed all relevant parts of the document:
        1. **Retrieve**: Use the `query_document` tool to analyze a specific component or area of the system.
        2. **Research**: Use the `web_search` tool to find known vulnerabilities matching what you found (e.g., CVEs, OWASP entries).
        3. **Store**: Use the `add_vulnerability` tool immediately to store any vulnerabilities you discover.
        
        CRITICAL: Repeat steps 1-3 in a loop. Do not stop after a single tool call. Continue querying, researching, and storing until you are certain you have covered the entire document.
        
        4. **Review**: Once the document is fully analyzed, use the `read_vulnerabilities` tool to retrieve the complete list of stored vulnerabilities.
        5. **Finish**: Call the `finish` tool to end the audit.

        ## Rules
        - Prioritize attack surface: auth, inputs, network exposure, third-party deps, secrets handling, privilege boundaries.
        - Cross-reference document findings with current threat intelligence (2025 onwards).
        - Never assume a component is secure without querying and searching it.
        - Escalate query specificity if initial results are vague.
        - When adding a vulnerability, use the bounding box and page number of the document chunk that you are referencing.
        """

    def with_overrides(self, **kwargs) -> "PipelineConfig":
        return replace(self, **kwargs)
