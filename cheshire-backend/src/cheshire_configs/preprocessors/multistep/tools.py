from typing import Annotated, Any
from haystack.tools import tool

from globals import DATA_PATH
from knowledge_base.qdrant import QdrantRepositoryManager

_chunks_cache: list = []

def set_chunks_cache(chunks: list) -> None:
    global _chunks_cache
    _chunks_cache = chunks

@tool
def get_standard(
    standard_id: Annotated[str, "The standard ID to retrieve."]
) -> dict[str, Any]:
    """
    Gets facts relevant to the standard.

    :param standard_id: the standard ID to get relevant facts for.

    :return: a dict containing result string with all facts relevant to the standard.
    """
    _, knowledge_repo = QdrantRepositoryManager.get_repositories(DATA_PATH, username="system")
    results = knowledge_repo.search(query=standard_id)
    facts: list[str] = [f"{document.content} (id: {document.id})" for document in results]
    return {"facts": facts}

@tool
def query_other_section(
    section_title: Annotated[str, "The title or heading of the section to query (e.g. 'Authentication', 'Section 5')."]
) -> str:
    """
    Retrieves the full text of another section in the document by title search.
    Use this when you see a reference to another section or component that is not
    fully detailed in the current section text.

    :param section_title: the title or heading of the section to retrieve.
    :return: the text of the matching section, or a warning if not found.
    """
    global _chunks_cache
    if not _chunks_cache:
        return "Warning: Document content is not cached or available for search."
        
    matches = []
    for chunk in _chunks_cache:
        if section_title.lower() in chunk.heading.lower():
            matches.append(
                f"--- Section: {chunk.heading} (pages {chunk.page_range[0]}-{chunk.page_range[1]}) ---\n"
                f"{chunk.structured_text}"
            )
            
    if matches:
        return "\n\n".join(matches)
        
    return f"Warning: No sections found matching title '{section_title}'."
