# Contributing

Anchor is a local-first project. Keep changes small, explain behavior changes
clearly, and avoid committing generated data or local credentials.

## Local Setup

```bash
npm install
cd backend
uv sync
copy .env.example .env
cd ..
npm run dev
```

Fill in `backend/.env` with your own LLM provider credentials before starting
the app.

## Before Opening a Pull Request

- Run the app locally with `npm run dev`.
- Keep `backend/data/`, `.next/`, `node_modules/`, `.venv/`, logs, and cache
  files out of commits.
- Do not commit third-party datasheets, private documents, FMUs, generated
  medallion artifacts, screenshots, or credentials unless their license and
  purpose are documented.
- Add focused tests or smoke-test notes for behavior changes.
- Keep documentation factual and current with the code.

## Development Notes

- Frontend code lives in `src/`.
- Backend code lives in `backend/`.
- The current runtime uses JSON-file-backed document and conversation stores.
- PostgreSQL/pgvector configuration may exist for future work, but it is not
  required for the default local workflow.
