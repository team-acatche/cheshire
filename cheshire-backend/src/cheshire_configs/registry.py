from cheshire_configs.core import Provider, PipelineConfig
from cheshire_configs.ollama import ollama_config


async def configs() -> dict[Provider, PipelineConfig]:
    return {
        Provider.OLLAMA: await ollama_config(),
    }
