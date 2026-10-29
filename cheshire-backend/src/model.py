from dotenv import load_dotenv
# Check if .env.user exists; if it does, load it
load_dotenv("../.env.user", verbose=True)
load_dotenv()

import logging
logger = logging.getLogger("uvicorn.error")

from pathlib import Path
from typing import Optional
from knowledge_base.job_store import CancelCheck
from knowledge_base.repository import KnowledgeRepository

from tools.helpers.output_schema import VulnerabilityDetails
from cheshire_configs.core import PipelineConfig
from cheshire_configs.preprocessors.multistep.steps import run_pass1, run_pass2, PreprocessingPassResults

async def evaluate_file(
    document_path: Path,
    config: PipelineConfig,
    should_cancel: Optional[CancelCheck] = None,
    knowledge_repo: Optional[KnowledgeRepository] = None,
) -> Optional[list[VulnerabilityDetails]]:
    results: PreprocessingPassResults = run_pass1(str(document_path), should_cancel=should_cancel, knowledge_repo=knowledge_repo)
    return run_pass2(results, should_cancel=should_cancel, knowledge_repo=knowledge_repo)
