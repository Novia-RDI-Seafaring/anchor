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
4. Visualize (dashboard notebook):
   - Open `backend/evals/runs_dashboard.ipynb` and run all cells.
5. Clear logs between runs:
    ```bash
    python -c "from evals.trace_logger import clear_log; clear_log()"
    ```

## Eval runners

These runners generate additional `*_eval_*` events in `logs/runs.jsonl`.

- Retrieval accuracy:
  - Dataset: `backend/evals/datasets/retrieval_gold.jsonl`
  - Run: `python backend/evals/run_retrieval_eval.py --dataset backend/evals/datasets/retrieval_gold.jsonl`
- Answer groundedness (agent + LLM judge):
  - Dataset: `backend/evals/datasets/qa_gold.jsonl`
  - Run (example): `python backend/evals/run_groundedness_eval.py --model-id azure:novia-gpt-5-nano --grader-model my-o4-mini`

## Tips
- If you are repeatedly ingesting the same documents for experiments, set `SKIP_DUPLICATE_INGEST=1` on the backend to skip duplicate ingests (based on `content_hash` / `source_url`).
- For groundedness scoring, keep a stable grader model (typically an Azure deployment) so comparisons across Azure/Ollama runs are meaningful.

## Files
- `runs_dashboard.ipynb` - visualizes `logs/runs.jsonl` (tables + charts + HTML export).
- `trace_logger.py` - appends JSONL logs.
- `token_utils.py` - token estimations with `tiktoken` fallback.
- `summarize.py` - aggregates logs (token/latency stats).
- `run_retrieval_eval.py` - runs retrieval accuracy cases (recall/MRR).
- `run_groundedness_eval.py` - runs agent answers + LLM judge grading.
- `datasets/` - JSONL datasets for eval runners.
