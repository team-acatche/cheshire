import os

from haystack_integrations.components.generators.togetherai import TogetherAIChatGenerator
from cheshire_configs.core import DefaultToolFactory, PipelineConfig


async def together_config() -> PipelineConfig:
    from dotenv import load_dotenv
    load_dotenv()

    return PipelineConfig(
        model=TogetherAIChatGenerator(
            model=os.getenv("TOGETHER_CHAT_MODEL", "ServiceNow-AI/Apriel-1.6-15b-Thinker"),
            generation_kwargs={
                "reasoning_effort": os.getenv("TOGETHER_REASONING_EFFORT", "medium"),
                "stream": True,
            }
        ),
        tools=DefaultToolFactory().tools,
    )