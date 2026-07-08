from fastapi import HTTPException, status

from cheshire_configs.core import EvaluationType, Provider, PipelineConfig
from cheshire_configs.openrouter import openrouter_config

async def resolve_config(
    provider: Provider = Provider.OPENROUTER,
    evaluation_mode: EvaluationType = EvaluationType.MULTISTEP,
) -> PipelineConfig:
    match provider:
        case Provider.OPENROUTER:
            return (await openrouter_config()).with_overrides(mode=evaluation_mode)
        case _:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported pipeline: {provider}")
