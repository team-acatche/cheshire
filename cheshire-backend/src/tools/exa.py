from haystack_integrations.components.websearch.exa import ExaWebSearch
from haystack.tools.component_tool import ComponentTool

from tools.helpers.document_to_string import document_to_string

from dotenv import load_dotenv

load_dotenv()

web_search = ComponentTool(
	component=ExaWebSearch(
		type="fast",
		include_domains=["nvd.nist.gov"],
		start_published_date="2025-01-01T00:00:00.000Z",
		# Token Optimizations
		text=False,
		summary=False,
		highlights={"maxCharacters": 2000},
	),
	name="web_search",
	description="Answer questions through the web using Exa search.",
	parameters={
		"type": "object",
		"properties": {
			"query": {
				"type": "string",
				"description": "The question to answer.",
			},
		},
		"required": ["query"],
	},
	outputs_to_string={"source": "answer", "handler": str}
)