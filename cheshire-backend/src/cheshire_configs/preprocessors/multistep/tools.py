from typing import Annotated, Any
from haystack.tools import tool

from globals import DATA_PATH
from knowledge_base.qdrant import QdrantRepositoryManager

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
