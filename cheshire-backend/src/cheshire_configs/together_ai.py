import os

from haystack_integrations.components.generators.togetherai import TogetherAIChatGenerator
from haystack_integrations.components.embedders.fastembed import FastembedTextEmbedder, FastembedDocumentEmbedder

from cheshire_configs.core import DefaultToolFactory, PipelineConfig

import json
import re
import uuid
from typing import Any

from haystack import component
from haystack.dataclasses import ChatMessage, ToolCall
from haystack.tools import Tool, Toolset

@component
class RawToolCallParserChatGenerator:
    def __init__(self, generator):
        self.generator = generator

    @component.output_types(replies=list[ChatMessage])
    def run(
        self,
        messages: list[ChatMessage],
        generation_kwargs: dict[str, Any] | None = None,
        tools: list[Tool | Toolset] | Toolset | None = None,
        **kwargs,
    ):
        result = self.generator.run(messages, generation_kwargs=generation_kwargs, tools=tools, **kwargs)
        replies = result["replies"]
        
        parsed_replies = []
        for reply in replies:
            if reply.text:
                match = re.search(r'Tool:\s*([^\n]+)\nArguments:\s*(.*?)(?:<tool_call\|>|$)', reply.text, re.DOTALL)
                if match:
                    tool_name = match.group(1).strip()
                    try:
                        arguments = json.loads(match.group(2).strip())
                        tool_call = ToolCall(tool_name=tool_name, arguments=arguments, id=f"call_{uuid.uuid4().hex[:8]}")
                        
                        clean_text = reply.text.replace(match.group(0), "").strip()
                        if not clean_text:
                            clean_text = None
                            
                        parsed_replies.append(
                            ChatMessage.from_assistant(
                                text=clean_text,
                                meta=reply.meta,
                                name=reply.name,
                                tool_calls=[tool_call]
                            )
                        )
                        continue
                    except json.JSONDecodeError:
                        pass
            parsed_replies.append(reply)
            
        return {"replies": parsed_replies}

async def together_config() -> PipelineConfig:
    # Force fastembed (onnxruntime) to use CPU to avoid NVRTC/CUDA initialization crashes
    os.environ["CUDA_VISIBLE_DEVICES"] = ""

    from dotenv import load_dotenv
    load_dotenv(".env.user")

    base_generator = TogetherAIChatGenerator(
        model=os.getenv("TOGETHER_CHAT_MODEL", "ServiceNow-AI/Apriel-1.6-15b-Thinker"),
        generation_kwargs={
            "reasoning_effort": os.getenv("TOGETHER_REASONING_EFFORT", "medium"),
            "stream": True,
        }
    )

    return PipelineConfig(
        model=RawToolCallParserChatGenerator(base_generator),
        embedder=lambda: FastembedTextEmbedder(model="sentence-transformers/all-MiniLM-L6-v2"),
        document_embedder=lambda: FastembedDocumentEmbedder(model="sentence-transformers/all-MiniLM-L6-v2"),
        tools=DefaultToolFactory().tools,
    )