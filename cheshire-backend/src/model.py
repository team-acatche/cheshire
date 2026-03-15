import asyncio

from dotenv import load_dotenv
load_dotenv()

from fastapi import HTTPException
import os
from pathlib import Path
from typing import Callable, Optional

import logging
logger = logging.getLogger("uvicorn.error")

from haystack.core.pipeline import Pipeline
from haystack.document_stores.types import DocumentStore
from haystack.components.generators.chat.llm import ChatGenerator, ChatMessage
from haystack.components.generators.utils import print_streaming_chunk
from haystack.tools import ToolsType
from haystack.components.agents import Agent

from tools.helpers.output_schema import VulnerabilityDetails
from cheshire_configs.core import PipelineConfig, EvaluationType

async def evaluate_file(document_path: Path, config: PipelineConfig) -> Optional[list[VulnerabilityDetails]]:
	if document_path.suffix != ".pdf" or not document_path.exists():
		return None

	if config.preprocessor and config.document_store:
		logger.info(f"agent({document_path.name}): Preprocessing...")
		config.preprocessor(document_path, config.document_store)
		logger.info(f"agent({document_path.name}): File preprocessing complete.")

	system_prompt = config.system_prompt
	# Retrieve the orientation bundle documents
	if config.document_store:
		logger.info(f"agent({document_path.name}): Retrieving orientation bundle...")
		try:
			skeleton_docs = config.document_store.filter_documents(
				{"field": "meta.type", "operator": "==", "value": "orientation_skeleton"}
			)
			visual_index_docs = config.document_store.filter_documents(
				{"field": "meta.type", "operator": "==", "value": "orientation_visual_index"}
			)

			orientation_text = ""
			if skeleton_docs:
				orientation_text += f"\n## Document Skeleton\n{skeleton_docs[0].content}\n"
			if visual_index_docs:
				orientation_text += f"\n## Visual Index\n{visual_index_docs[0].content}\n"
			
			if orientation_text:
				system_prompt += f"\n\nHere is the orientation bundle for the document you are analyzing. Use it to understand the structure and locate specific sections or figures before querying:\n{orientation_text}"
			logger.info(f"agent({document_path.name}): Orientation bundle retrieved.")
		except Exception as e:
			logger.error(f"Failed to retrieve orientation bundle: {e}")

	logger.info(f"agent({document_path.name}): Starting audit...")
	analyst = Agent(
		chat_generator=config.model,
		system_prompt=system_prompt,
		tools=config.tools,
		exit_conditions=["text"],
		streaming_callback=print_streaming_chunk, # TODO (feat): switch to logger
		state_schema={
			"vulnerabilities_list": {"type": list[VulnerabilityDetails]},
		}
	)

	messages: list[ChatMessage] = []
	if config.mode == EvaluationType.FULL_DOCUMENT:
		from haystack.components.converters.image import PDFToImageContent

		logger.info(f"agent({document_path.name}): Converting PDF to images...")
		converter = PDFToImageContent()
		pages = converter.run(sources=[document_path])["image_contents"]
		assert len(pages) > 0
		logger.info(f"agent({document_path.name}): PDF converted to images.")

		messages.append(ChatMessage.from_user(content_parts=["Audit the following file:", *pages]))
	else:
		messages.append(ChatMessage.from_user("Start the audit"))

	response = analyst.run(messages=messages)
	logger.info(f"agent({document_path.name}): Audit complete.")

	return response.get("vulnerabilities_list", [])
