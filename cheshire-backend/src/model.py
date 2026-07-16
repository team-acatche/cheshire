from dotenv import load_dotenv
# Check if .env.user exists; if it does, load it
load_dotenv("../.env.user", verbose=True)
load_dotenv()

import logging
logger = logging.getLogger("uvicorn.error")

from pathlib import Path
from typing import Optional

from tools.helpers.output_schema import VulnerabilityDetails
from cheshire_configs.core import PipelineConfig
from cheshire_configs.preprocessors.multistep.steps import run_pass1, run_pass2, PreprocessingPassResults

async def evaluate_file(document_path: Path, config: PipelineConfig) -> Optional[list[VulnerabilityDetails]]:
	results: PreprocessingPassResults = run_pass1(str(document_path))
	return run_pass2(results)
