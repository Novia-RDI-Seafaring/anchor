import os
import sys
from dotenv import load_dotenv

# Add backend to path to allow imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from src.core import logging # Initialize Logfire first
from src.observability.langfuse.config import init_langfuse
from src.agent.agent import agent
from pydantic_ai.messages import ModelMessage
from pydantic_ai.ag_ui import StateDeps
from src.agent.state import RAGState
import asyncio

async def test_tracing():
    print("Initializing Langfuse...")
    init_langfuse()
    
    print("Running a test query through the agent...")
    # Mock dependencies
    deps = StateDeps(RAGState())
    
    # Run a simple query
    try:
        result = await agent.run("Hello, who are you?", deps=deps)
        print(f"Agent response: {result.data[:100]}...")
        print("Traces should have been sent to both Logfire and Langfuse.")
        print("Please check your dashboards.")
    except Exception as e:
        print(f"Error during test: {e}")

if __name__ == "__main__":
    load_dotenv()
    asyncio.run(test_tracing())
