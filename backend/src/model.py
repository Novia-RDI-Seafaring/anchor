from .types import *

logger = getLogger(__name__)
# Load environment variables
load_dotenv(override=True)

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


def get_default_responses_model(model_name: str | None = None, provider: str | None = None):
    """
    Get OpenAIResponsesModel (ag-ui compatible wrapper) using default configuration.
    
    Args:
        model_name: Optional model name override. If None, uses DEFAULT_MODEL env var.
        provider: Optional provider override. If None, uses DEFAULT_PROVIDER env var.
    
    Returns:
        OpenAIResponsesModel instance configured with default settings.
    """
    from pydantic_ai.models.openai import OpenAIResponsesModel
    
    # Get the base model to extract model_name if not provided
    base_model = get_default_model(model_name or default_model, provider or default_provider)
    
    # Extract the model name from the OpenAIChatModel
    model_name_str = base_model.model_name if hasattr(base_model, 'model_name') else (model_name or default_model)
    
    # Get the provider to use
    current_provider = provider or default_provider
    
    # OpenAIResponsesModel supports provider parameter including 'azure'
    return OpenAIResponsesModel(
        model_name_str,
        provider=current_provider
    )