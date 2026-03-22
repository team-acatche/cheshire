from haystack_integrations.components.websearch.exa import ExaAnswer
from haystack.tools.component_tool import ComponentTool

from tools.helpers.document_to_string import document_to_string

from dotenv import load_dotenv

load_dotenv()

web_search = ComponentTool(
	component=ExaAnswer(system_prompt="Provide a concise, factual answer to the query (strictly under 500 tokens). Prioritize results from 2025 or later. Always explicitly cite specific sources from the provided search results to support your claims."),
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