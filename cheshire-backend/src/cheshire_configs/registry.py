from cheshire_configs.core import Provider, PipelineConfig
from cheshire_configs.openrouter import openrouter_config


async def configs() -> dict[Provider, PipelineConfig]:
    return {
        Provider.OPENROUTER: await openrouter_config(),
    }
