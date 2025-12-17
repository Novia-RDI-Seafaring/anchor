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





def _last_user_prompt_index(messages: list[ModelMessage]) -> int | None:
    for idx in range(len(messages) - 1, -1, -1):
        msg = messages[idx]
        if getattr(msg, "kind", None) != "request":
            continue
        parts = getattr(msg, "parts", None) or []
        for part in parts:
            if getattr(part, "part_kind", None) == "user-prompt":
                return idx
    return None


def _tool_seen_since(messages: list[ModelMessage], *, since_idx: int, tool_name: str) -> bool:
    for msg in messages[since_idx + 1 :]:
        for part in getattr(msg, "parts", None) or []:
            kind = getattr(part, "part_kind", None)
            if kind in {"tool-call", "builtin-tool-call", "tool-return", "builtin-tool-return"}:
                if getattr(part, "tool_name", None) == tool_name:
                    return True
    return False


def _enforce_tools_for_turn(messages: list[ModelMessage], model_request_parameters: ModelRequestParameters) -> ModelRequestParameters:
    """
    Enforce that each user turn triggers KB retrieval before the model can answer with plain text.

    This addresses cases where models ignore the system prompt and answer generically without calling tools.
    """
    if os.getenv("ENFORCE_RAG_TOOLING", "1").strip().lower() in {"0", "false", "no", "n"}:
        return model_request_parameters

    user_idx = _last_user_prompt_index(messages)
    if user_idx is None:
        return model_request_parameters

    has_kb = _tool_seen_since(messages, since_idx=user_idx, tool_name="query_knowledge_base")
    has_render = _tool_seen_since(messages, since_idx=user_idx, tool_name="render_ui_component")
    require_render = os.getenv("ENFORCE_UI_RENDER", "0").strip().lower() in {"1", "true", "yes", "y"}

    # Force tool calling until retrieval (and optionally rendering) has happened for this user prompt.
    # Requiring rendering by default can cause tool-call loops if the model keeps choosing retrieval again.
    if not has_kb or (require_render and not has_render):
        return replace(model_request_parameters, allow_text_output=False)
    return model_request_parameters

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
        if model_request_parameters is not None:
            model_request_parameters = _enforce_tools_for_turn(messages, model_request_parameters)

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
    ) -> Any:
        model = self._get_current_model()
        model_name = getattr(model, "model_name", None)
        provider = getattr(model, "_provider", default_provider)
        if model_request_parameters is not None:
            model_request_parameters = _enforce_tools_for_turn(messages, model_request_parameters)

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
