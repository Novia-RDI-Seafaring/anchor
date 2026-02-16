import os
import base64
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
import logging

logger = logging.getLogger(__name__)

def init_langfuse():
    """
    Initializes Langfuse as an additional OpenTelemetry exporter.
    This works alongside Logfire by adding a new span processor to the global tracer provider.
    """
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    host = os.getenv("LANGFUSE_HOST") or os.getenv("LANGFUSE_BASE_URL") or "https://cloud.langfuse.com"

    if not public_key or not secret_key:
        logger.info("Langfuse keys not found, skipping Langfuse initialization")
        return

    # Langfuse OTLP endpoint
    endpoint = f"{host.rstrip('/')}/api/public/otel/v1/traces"
    
    # Create Basic Auth header for Langfuse
    auth = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth}"
    }

    try:
        # Get the global tracer provider
        # Logfire usually sets this up. If not yet set, we might need to initialize it.
        provider = trace.get_tracer_provider()
        
        # If it's a ProxyTracerProvider (default before any real provider is set), 
        # we might need to be careful. But Logfire usually initializes it early in main.py.
        if not isinstance(provider, TracerProvider):
            # If Logfire hasn't initialized yet, we create a provider.
            # However, Logfire should lead the OTel setup.
            # We'll assume Logfire has started or will start.
            logger.warning("Global TracerProvider is not an SDK TracerProvider. Langfuse might not hook correctly if Logfire isn't configured first.")

        # Create the Langfuse OTLP/HTTP exporter
        exporter = OTLPSpanExporter(
            endpoint=endpoint,
            headers=headers
        )

        # Add the span processor to the provider
        # This allows multiple processors (Logfire + Langfuse)
        span_processor = BatchSpanProcessor(exporter)
        
        # We need to add it to the tracer provider. 
        # If it's the standard SDK TracerProvider, we can call add_span_processor.
        if hasattr(provider, "add_span_processor"):
            provider.add_span_processor(span_processor)
            logger.info("Langfuse OpenTelemetry exporter added successfully")
        else:
            logger.error("Could not add Langfuse span processor: TracerProvider does not support add_span_processor")

    except Exception as e:
        logger.error(f"Failed to initialize Langfuse: {e}")

if __name__ == "__main__":
    # Test initialization
    from dotenv import load_dotenv
    load_dotenv()
    init_langfuse()
