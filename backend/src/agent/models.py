from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager
from logging import getLogger
from typing import Any, AsyncIterator, Literal

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic_ai import ModelResponse
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import Model, ModelRequestParameters
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers import Provider
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import Usage

from evals.token_utils import estimate_tokens
from evals.trace_logger import log_event
from src.core.context import get_current_model_id
from .utils import enforce_tools_for_turn

logger = getLogger(__name__)
# Load environment variables
load_dotenv(override=True)

# Normalize Ollama env var naming to avoid misconfiguration
if not os.getenv("OLLAMA_URL") and os.getenv("OLLAMA_BASE_URL"):
    os.environ["OLLAMA_URL"] = os.getenv("OLLAMA_BASE_URL")

default_provider = os.getenv("DEFAULT_PROVIDER", None)
default_model = os.getenv("DEFAULT_MODEL", None)

if os.getenv("AZURE_OPENAI_API_KEY", os.getenv("OPENAI_API_KEY", None)) is not None:

    default_provider = "azure" if os.getenv("AZURE_OPENAI_API_KEY") is not None else "openai"
    match default_provider:
        case "azure":
            assert os.getenv("AZURE_OPENAI_ENDPOINT") is not None, "AZURE_OPENAI_ENDPOINT is not set"
            assert os.getenv("AZURE_OPENAI_API_KEY") is not None, "AZURE_OPENAI_API_KEY is not set"
            assert os.getenv("OPENAI_API_VERSION") is not None, "OPENAI_API_VERSION is not set" # see the docstring in class AzureProvider
            logger.info("Using Azure OpenAI as the default provider")
            default_provider = "azure"
            default_model = os.getenv("AZURE_OPENAI_DEPLOYMENT", default_model)
        case "openai":
            assert os.getenv("OPENAI_API_KEY") is not None, "OPENAI_API_KEY is not set"
            # Allow OPENAI_MODEL to override DEFAULT_MODEL, similar to Azure's AZURE_OPENAI_DEPLOYMENT
            default_model = os.getenv("OPENAI_MODEL", default_model)
            default_provider = "openai"

else:
    logger.warning("""
        No default provider found. Please configure one of the following:
        - To use OpenAI, set the OPENAI_API_KEY environment variable.
        - To use Azure OpenAI, set the following env variables:
            - AZURE_OPENAI_ENDPOINT (the endpoint of the Azure OpenAI service)
            - AZURE_OPENAI_API_KEY (the API key of the Azure OpenAI service)
            - OPENAI_API_VERSION (this is used by the AzureProvider class to set the API version)
        - Alternatively, set DEFAULT_PROVIDER and DEFAULT_MODEL environment variables.
    """)
assert default_provider is not None, "No default provider configured, set one with the DEFAULT_PROVIDER env variable"
assert default_provider in ['azure', 'deepseek', 'cerebras', 'fireworks', 'github', 'grok', 'heroku', 'moonshotai', 'ollama', 'openai', 'openai-chat', 'openrouter', 'together', 'vercel', 'litellm', 'nebius', 'ovhcloud', 'gateway'], f"Default provider must be a Provider or a string: {type(default_provider)}, {default_provider}"
assert default_model is not None, "No default model configured, set one with the DEFAULT_MODEL env variable"

def get_default_model(model_name: str = default_model, provider: Provider[AsyncOpenAI] | Literal['azure', 'deepseek', 'cerebras', 'fireworks', 'github', 'grok', 'heroku', 'moonshotai', 'ollama', 'openai', 'openai-chat', 'openrouter', 'together', 'vercel', 'litellm', 'nebius', 'ovhcloud', 'gateway'] = default_provider) -> OpenAIChatModel:
    global default_provider, default_model
    assert model_name is not None, "No default model configured. Set DEFAULT_MODEL environment variable or pass model_name parameter."
    assert provider is not None, "No default provider configured. Set DEFAULT_PROVIDER environment variable or pass provider parameter."
    return OpenAIChatModel(
        model_name=model_name.split(':')[1] if ':' in model_name else model_name,
        provider=provider
    )




class DynamicChatModel(Model):
    """
    A Model wrapper that dynamically switches between different LLM models
    based on runtime context (e.g., from a global variable or database).
    """
    def __init__(self, default_model: Model):
        self.default_model = default_model
        self._model_cache = {}

    def _get_current_model(self) -> Model:
        model_id = get_current_model_id()
        if not model_id:
            return self.default_model
            
        if model_id in self._model_cache:
            return self._model_cache[model_id]
            
        # Create new model instance
        provider = "openai"  # default
        model_name = model_id
        
        if model_id.startswith("ollama:"):
            provider = "ollama"
            model_name = model_id.split(":", 1)[1]
        elif model_id.startswith("azure:"):
            provider = "azure"
            model_name = model_id.split(":", 1)[1]
            
        from pydantic_ai.models.openai import OpenAIModel
        
        print(f"DynamicChatModel: Switching to {model_name} (provider: {provider})")
        
        if provider == "ollama":
            new_model = OpenAIModel(model_name, provider='ollama')
        else:
            new_model = OpenAIModel(model_name, provider=provider)

        self._model_cache[model_id] = new_model
        return new_model

    @property
    def model_name(self) -> str:
        # Note: This is sync but _get_current_model is async now
        # For property access, we'll need to handle this carefully
        # Since model_name is typically accessed synchronously, we keep cached model
        model_id = get_current_model_id()
        if not model_id or model_id not in self._model_cache:
            return self.default_model.model_name
        return self._model_cache[model_id].model_name

    @property
    def system(self) -> str | None:
        model_id = get_current_model_id()
        if not model_id or model_id not in self._model_cache:
            return self.default_model.system
        return self._model_cache[model_id].system

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None = None,
        model_request_parameters: ModelRequestParameters | None = None,
    ) -> tuple[ModelResponse, Usage]:
        """Make async request with thread-safe model retrieval."""
        current_model = self._get_current_model()  # Now synchronous
        return await current_model.request(messages, model_settings, model_request_parameters)

    def request_stream(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters | None,
        *args,
        **kwargs,
    ) -> Any:
        model = self._get_current_model()
        model_name = getattr(model, "model_name", None)
        provider = getattr(model, "_provider", default_provider)
        if model_request_parameters is not None:
            model_request_parameters = enforce_tools_for_turn(messages, model_request_parameters)

        stream_or_cm = model.request_stream(messages, model_settings, model_request_parameters, *args, **kwargs)

        # pydantic-ai's streaming API may return either an async iterator or an async context manager.
        # Wrap both forms while preserving the original protocol.
        if hasattr(stream_or_cm, "__aenter__") and hasattr(stream_or_cm, "__aexit__"):

            @asynccontextmanager
            async def _cm():
                started = time.perf_counter()
                try:
                    async with stream_or_cm as stream:
                        yield stream
                finally:
                    latency_ms = (time.perf_counter() - started) * 1000
                    try:
                        log_event(
                            {
                                "type": "llm_call",
                                "model": model_name,
                                "provider": provider,
                                "message_count": len(messages) if messages else 0,
                                "prompt_tokens_est": 0,
                                "usage": {},
                                "latency_ms": latency_ms,
                                "stream": True,
                            }
                        )
                    except Exception:
                        pass

            return _cm()

        async def _gen() -> AsyncIterator[Any]:
            started = time.perf_counter()
            try:
                async for item in stream_or_cm:
                    yield item
            finally:
                latency_ms = (time.perf_counter() - started) * 1000
                try:
                    log_event(
                        {
                            "type": "llm_call",
                            "model": model_name,
                            "provider": provider,
                            "message_count": len(messages) if messages else 0,
                            "prompt_tokens_est": 0,
                            "usage": {},
                            "latency_ms": latency_ms,
                            "stream": True,
                        }
                    )
                except Exception:
                    pass

        return _gen()

def get_default_responses_model(model_name: str | None = None, provider: str | None = None):
    """
    Get DynamicChatModel wrapping the default model.
    """
    # Base default model
    base_model = get_default_model(model_name or default_model, provider or default_provider)
    
    # Return dynamic wrapper
    return DynamicChatModel(base_model)
