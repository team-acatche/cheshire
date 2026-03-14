from enum import StrEnum, auto
from dataclasses import dataclass, field, replace
from typing import Protocol, runtime_checkable, Optional
from pathlib import Path
from haystack.core.pipeline import Pipeline
from haystack.document_stores.types import DocumentStore
from haystack.components.generators.chat.llm import ChatGenerator, ChatMessage
from haystack.components.embedders.types import TextEmbedder
from haystack.tools import ToolsType

from tools.base import add_vulnerability_tool, read_vulnerabilities_tool
from tools.exa import web_search

class EvaluationType(StrEnum):
    RAG = auto()
    FULL_DOCUMENT = auto()

class Provider(StrEnum):
    OLLAMA = auto()
    TOGETHER_AI = auto()

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
    extra_tools: list = field(default_factory=list)

    @property
    def tools(self) -> ToolsType:
        return [
            web_search,
            add_vulnerability_tool("vulnerabilities_list"),
            read_vulnerabilities_tool("vulnerabilities_list")
        ] + self.extra_tools
    
    def extend(self, factory: ToolFactory):
        self.extra_tools.extend(factory.tools)

@dataclass(frozen=True)
class PipelineConfig:
    model: ChatGenerator
    tools: ToolsType = field(default_factory=list)
    mode: EvaluationType = EvaluationType.RAG
    document_store: Optional[DocumentStore] = None
    preprocessor: Optional[DocumentPreprocessor] = None
    embedder: Optional[TextEmbedder] = None
    system_prompt: str = """
        You are an expert security auditor. Given the system overview below, identify vulnerabilities by reading the document and cross-referencing known CVEs and attack patterns online.
        ## Process
        Repeat the following process until the full document has been covered:
        1. **Know**: Plan your analysis.
        2. **Plan**: Identify a specific component or area to investigate next.
        3. **Research**: Use `web_search` to find known vulnerabilities matching what you found (e.g., CVEs, OWASP entries, exploit patterns). Ensure that what you're searching is specific to the component you're investigating.
        Repeat steps 1-3 until you are certain you have analyzed the entire document.
        4. **Store**: Use `add_vulnerability` to store the vulnerabilities you found to combine later into a final report.
        ## Rules
        - Prioritize attack surface: auth, inputs, network exposure, third-party deps, secrets handling, privilege boundaries.
        - Cross-reference document findings with current threat intelligence.
        - Never assume a component is secure without querying and searching it.
        - Ensure that the vulnerabilites and recommendations are as relevant and as recent as possible to the document you are analyzing.
        - Escalate query specificity if initial results are vague.
        - When adding a vulnerability, use the bounding box and page number of the document chunk that you are referencing.
        - To ensure that the final response is lossless, use `read_vulnerabilities` to read the vulnerability list before producing the final summary.
        """

    def with_overrides(self, **kwargs) -> "PipelineConfig":
        return replace(self, **kwargs)
