from .types import *

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


from datetime import timedelta
from typing import Any, AsyncIterator, Iterator, Sequence
import time

from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models import Model, ModelRequestParameters
from pydantic_ai.settings import ModelSettings
from src.request_context import get_current_model_id
from pydantic_ai.models.openai import OpenAIResponsesModel # This import is not used in the new get_default_responses_model, but was in the old one. Keeping it for now.
from evals.trace_logger import log_event
from evals.token_utils import estimate_tokens

class DynamicChatModel(Model):
    """
    A wrapper model that dynamically selects the underlying model 
    based on the current request context.
    """
    
    def __init__(self, default_model: Model):
        self.default_model = default_model
        self._model_cache = {}

    def _get_current_model(self) -> Model:
        model_id = get_current_model_id()
        if not model_id:
            return self.default_model
            
        # If it's the same as default, return default
        # (This check is simplistic as default_model might not expose its name easily in a standard way,
        # but let's assume we want to switch if ID is present)
        
        if model_id in self._model_cache:
            return self._model_cache[model_id]
            
        # Create new model instance
        # Handle "ollama:", "azure:", etc. prefixes
        provider = "openai" # default
        model_name = model_id
        
        if model_id.startswith("ollama:"):
            provider = "ollama"
            model_name = model_id.split(":", 1)[1]
        elif model_id.startswith("azure:"):
            provider = "azure"
            model_name = model_id.split(":", 1)[1]
            
        # Instantiate OpenAIResponsesModel (ag-ui wrapper)
        # Note: ag-ui uses OpenAIResponsesModel which wraps pydantic_ai.models.openai.OpenAIModel
        # We need to return a Model compatible object.
        
        # We'll use the same helper as before but with explicit params
        from pydantic_ai.models.openai import OpenAIModel
        
        print(f"DynamicChatModel: Switching to {model_name} (provider: {provider})")
        
        if provider == "ollama":
             # For Ollama, we rely on pydantic_ai's native support
             # It likely defaults to localhost:11434 or uses env vars.
             new_model = OpenAIModel(
                 model_name,
                 provider='ollama'
             )
        else:
             # Azure or OpenAI
             new_model = OpenAIModel(
                 model_name,
                 provider=provider
             )

        self._model_cache[model_id] = new_model
        return new_model

    @property
    def model_name(self) -> str:
        return self._get_current_model().model_name

    @property
    def system(self) -> str | None:
        return self._get_current_model().system

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters | None,
        *args,
        **kwargs,
    ) -> tuple[ModelResponse, Any]:
        model = self._get_current_model()
        model_name = getattr(model, "model_name", None)
        provider = getattr(model, "_provider", default_provider)

        # Estimate prompt tokens best-effort
        try:
            prompt_tokens_est = 0
            for m in messages:
                content = getattr(m, "content", None)
                if isinstance(content, str):
                    prompt_tokens_est += estimate_tokens(content, model_name=model_name)
                elif isinstance(content, list):
                    # Some message bodies may be lists of parts; join as text for estimation
                    prompt_tokens_est += estimate_tokens(" ".join(str(p) for p in content), model_name=model_name)
        except Exception:
            prompt_tokens_est = 0

        started = time.perf_counter()
        response, meta = await model.request(
            messages, model_settings, model_request_parameters, *args, **kwargs
        )
        latency_ms = (time.perf_counter() - started) * 1000

        # Extract usage if available
        usage = {}
        try:
            resp_data = getattr(response, "response_data", None)
            if resp_data and isinstance(resp_data, dict):
                usage = resp_data.get("usage", {}) or {}
        except Exception:
            usage = {}

        try:
            log_event({
                "type": "llm_call",
                "model": model_name,
                "provider": provider,
                "message_count": len(messages) if messages else 0,
                "prompt_tokens_est": prompt_tokens_est,
                "usage": usage,
                "latency_ms": latency_ms,
            })
        except Exception:
            pass

        return response, meta

    def request_stream(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters | None,
        *args,
        **kwargs,
    ) -> AsyncIterator[Any]:
        return self._get_current_model().request_stream(
            messages, model_settings, model_request_parameters, *args, **kwargs
        )

def get_default_responses_model(model_name: str | None = None, provider: str | None = None):
    """
    Get DynamicChatModel wrapping the default model.
    """
    # Base default model
    base_model = get_default_model(model_name or default_model, provider or default_provider)
    
    # Return dynamic wrapper
    return DynamicChatModel(base_model)
