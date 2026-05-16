from cheshire_configs.core import Provider, PipelineConfig
from cheshire_configs.ollama import ollama_config
from cheshire_configs.together_ai import together_config
from cheshire_configs.openrouter import openrouter_config


async def configs() -> dict[Provider, PipelineConfig]:
    return {
        Provider.OLLAMA: await ollama_config(),
        Provider.TOGETHER_AI: await together_config(),
        Provider.OPENROUTER: await openrouter_config(),
    }
