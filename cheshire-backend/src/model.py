import asyncio

from dotenv import load_dotenv
load_dotenv()

from fastapi import HTTPException
import os
from pathlib import Path
from typing import Callable

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

async def evaluate_file(document_path: Path, config: PipelineConfig) -> list[VulnerabilityDetails] | None:
	if document_path.suffix != ".pdf" or not document_path.exists():
		return None

	if config.preprocessor and config.document_store:
		logger.info(f"agent({document_path.name}): Preprocessing...")
		config.preprocessor(document_path, config.document_store)
		logger.info(f"agent({document_path.name}): File preprocessing complete.")

	logger.info(f"agent({document_path.name}): Starting audit...")
	analyst = Agent(
		chat_generator=config.model,
		system_prompt=config.system_prompt,
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
		logger.info(f"agent({document_path.name}): PDF converted to images.")

		messages.append(ChatMessage.from_user(content_parts=["Audit the following file:", *pages]))
	else:
		messages.append(ChatMessage.from_user("Start the audit"))

	response = analyst.run(messages=messages)
	logger.info(f"agent({document_path.name}): Audit complete.")

	return response.get("vulnerabilities_list", [])
