from haystack_integrations.components.websearch.exa import ExaWebSearch
from haystack.tools.component_tool import ComponentTool
from haystack.dataclasses import Document

from dotenv import load_dotenv

load_dotenv()


def _format_search_results(documents: list[Document]) -> str:
    if not documents:
        return "No relevant web results found."
    formatted = []
    for i, doc in enumerate(documents, start=1):
        title = doc.meta.get("title") or "Untitled"
        url = doc.meta.get("url") or ""
        highlights = doc.meta.get("highlights")
        if highlights and isinstance(highlights, list):
            snippet = " ... ".join(str(h) for h in highlights)
        else:
            snippet = (doc.content or "")[:350].strip()
        formatted.append(f"[{i}] {title}\nURL: {url}\nExcerpt: {snippet}")
    return "\n\n".join(formatted)


web_search = ComponentTool(
    component=ExaWebSearch(
        num_results=3,
        highlights=True,
        type="auto",
    ),
    name="web_search",
    description="Search the web using Exa for software deprecation status, release dates, and official documentation.",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query to verify software deprecation or documentation.",
            },
        },
        "required": ["query"],
    },
    outputs_to_string={"source": "documents", "handler": _format_search_results},
)