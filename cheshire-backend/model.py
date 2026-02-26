import asyncio
from dotenv import load_dotenv
import os

from llama_index.core import Settings
from llama_index.core.agent.workflow import FunctionAgent
from llama_index.core.workflow import Context
from llama_index.llms.ollama import Ollama

def get_secret_code(name: str) -> str:
    """ Look up the secret code for a given person """
    SECRET_CODES = {
        "alice": "FOXTROT-8842",
        "bob": "TANGO-3197",
        "charlie": "ZULU-5503",
    }
    print(f"[TOOL CALLED] get_secret_code invoked with name='{name}'")
    return SECRET_CODES.get(name.lower(), "UNKNOWN PERSON")

async def main():
    load_dotenv()

    Settings.llm = Ollama(
        model=os.environ["OLLAMA_MODEL"],
        base_url=os.environ["OLLAMA_URL"],
        context_window=4096,
    )
    Settings.embed_model = HuggingFaceEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")

    agent = FunctionAgent(
        llm=Settings.llm,
        tools=[get_secret_code],
        system_prompt="You are an assistant that can look up secret codes for people. Use the get_secret_code tool to answer questions about secret codes.",
    )
    ctx = Context(agent)
    
    result = await agent.run("What is Bob's secret code?", context=ctx)
    print(str(result))

if __name__ == "__main__":
    asyncio.run(main())
