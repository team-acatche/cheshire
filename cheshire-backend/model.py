import asyncio
from agent_framework import ChatAgent
from agent_framework.openai import OpenAIChatClient
from dotenv import load_dotenv
import os

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

    agent = ChatAgent(
        chat_client=OpenAIChatClient(
            base_url=os.environ["OLLAMA_URL"],
            api_key="local_client",
            model_id=os.environ["OLLAMA_MODEL"]),
        instructions="You are an assistant that can look up secret codes for people. Use the get_secret_code tool to answer questions about secret codes.",
        tools=[get_secret_code]
    )
    
    result = await agent.run("What is Bob's secret code?")
    print(result.text)

if __name__ == "__main__":
    asyncio.run(main())
