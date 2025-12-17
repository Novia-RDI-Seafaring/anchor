# Eval Datasets

This folder holds lightweight JSONL datasets used by eval runners.

## Format: JSONL

One JSON object per line.

## Retrieval dataset (`retrieval_gold.jsonl`)

Each line:

```json
{
  "id": "case-001",
  "query": "What is the refund policy?",
  "top_k": 5,
  "active_document_id": null,
  "expected_document_ids": ["abc123def456"],
  "expected_filenames": ["policy.pdf"]
}
```

Notes:
- `expected_document_ids` and/or `expected_filenames` can be provided (both is best).
- `active_document_id` is optional; when set, the eval will apply a document filter (like the UI “active doc”).
- `top_k` is optional; the runner can override with a CLI flag.

## QA dataset (`qa_gold.jsonl`)

This is used by the groundedness runner. Each line:

```json
{
  "id": "case-001",
  "query": "Summarize the refund policy in 3 bullets.",
  "top_k": 5,
  "active_document_id": null,
  "expected_document_ids": ["abc123def456"],
  "expected_filenames": ["policy.pdf"],
  "must_include": ["time window", "exceptions"],
  "forbidden_claims": ["lifetime refunds"]
}
```

If you don’t have `must_include` / `forbidden_claims` yet, leave them as empty arrays.

