# Evals and Tracing

Lightweight instrumentation for RAG/LLM calls. Traces are written to `backend/evals/logs/runs.jsonl`.

## What gets logged
- Retrieval: query text length/tokens, `top_k`, result count, latency, per-chunk lengths.
- LLM calls: model/provider, message count, prompt token estimate, response usage (if provided), latency.
- Embeddings: model/provider, input lengths/tokens, batch sizes, latency.
- State size: counts of `conversation_history`, `last_chunks`, and `active_ui_components`.

## Usage
1. Set an optional run id: `export EVAL_RUN_ID=local-test-1`
2. Run your flow (agent or ingestion). Logs append to `logs/runs.jsonl`.
3. Summarize:
   ```bash
   python backend/evals/summarize.py
   ```
4. Clear logs between runs:
   ```bash
   python -c "from evals.trace_logger import clear_log; clear_log()"
   ```

## Files
- `trace_logger.py` – appends JSONL logs.
- `token_utils.py` – token estimations with `tiktoken` fallback.
- `summarize.py` – aggregates logs (token/latency stats).
