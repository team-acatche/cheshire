import asyncio
from llama_index.core.agent.workflow import FunctionAgent
from llama_index.llms.ollama import Ollama  # type: ignore[import-untyped]
from dotenv import load_dotenv
import os

def separate(value: int) -> list[int]:
    """ Separate a number into its individual digits """
    return sorted([int(digit) for digit in str(value)])

async def main():
    load_dotenv()

    # TODO: abstract the model into a protocol
    # TODO: add proper system prompt
    # TODO: find a way to give this agent a scratchpad
    agent = FunctionAgent(
        llm=Ollama(
            base_url=os.getenv("OLLAMA_URL"),
            model=os.getenv("OLLAMA_MODEL")
        ),
        tools=[separate],
        system_prompt="You are a helpful assistant that can perform an operation called 'separate' on a number."
    )

    result = await agent.run("Separate 49980")
    print(str(result))

if __name__ == "__main__":
    asyncio.run(main())
