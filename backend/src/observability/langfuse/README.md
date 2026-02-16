# Langfuse Observability Integration

This directory contains the integration for Langfuse observability, designed to work alongside the existing Logfire integration.

## How it works

The integration uses **OpenTelemetry (OTel)** to send traces to Langfuse. Since Pydantic AI is already instrumented with Logfire (which is also built on OTel), we simply add an additional `SpanProcessor` to the global OpenTelemetry `TracerProvider`.

This allows the application to "dual-export" traces to both Logfire and Langfuse simultaneously.

## Setup

1. Add the following environment variables to your `.env` file:
   ```env
   LANGFUSE_PUBLIC_KEY=your_public_key
   LANGFUSE_SECRET_KEY=your_secret_key
   LANGFUSE_HOST=https://cloud.langfuse.com
   ```

2. The integration is automatically initialized in `main.py` if these variables are present.

## Files

- `config.py`: Sets up the OpenTelemetry exporter for Langfuse.
- `verify_langfuse.py`: A script to verify that traces are being sent to Langfuse.
- `OBSERVABILITY_COMPARISON.md`: Documentation comparing the features and experience of Logfire vs Langfuse.

## Removal

To remove Langfuse, simply:
1. Delete this directory.
2. Remove the `init_langfuse()` call in `main.py`.
3. Remove the environment variables.
