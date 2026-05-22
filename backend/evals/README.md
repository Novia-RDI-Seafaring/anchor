# Backend Evals

This directory contains regression checks for document-grounded agent behavior.

## Canvas Fact Eval

Run from `backend/`:

```bash
uv run python evals/eval_agent_canvas_scalar.py
```

Run with another fixture:

```bash
uv run python evals/eval_agent_canvas_scalar.py --suite evals/fixtures/my_document.json
```

The default fixture is `evals/fixtures/lkh_canvas_facts.json`.

## Checks

- The agent answers document-grounded engineering questions from available source data.
- Scalar facts create a `fact` canvas node with evidence.
- Multi-value/table questions create a `spec` node with row-level sources.
- Source references include filename, page, and bbox where expected.
- Eval prompts are not copied into active agent instructions.

## Fixture Shape

Each suite defines one document and a list of cases:

```json
{
  "document": {
    "id": "example-doc",
    "filename": "Example Datasheet.pdf"
  },
  "cases": [
    {
      "name": "max-pressure",
      "prompt": "what is the max inlet pressure?",
      "expected_node_type": "fact",
      "expected_answer_terms": ["pressure", "1000", "kPa"],
      "expected_canvas_terms": ["pressure", "1000", "kPa"],
      "expected_page": 2
    }
  ]
}
```

Keep benchmark prompts in fixture files only. Do not hardcode them in `src/agent/prompts.py` or capability instructions.

## Logs

`evals/logs/` is for local run output. Commit logs only when they are part of a
baseline or report.
