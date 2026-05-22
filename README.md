# Anchor UI

Anchor UI is a local document-grounded engineering canvas. It ingests technical
PDFs, builds bronze/silver/gold document artifacts, and lets users place
source-backed facts, tables, images, and model nodes on a React Flow canvas.

The app has a Next.js frontend and a Python FastAPI backend. Chat and canvas
updates are routed through CopilotKit, AG-UI, and a PydanticAI agent.

## Run Locally

### Prerequisites

- Git
- Node.js 20 LTS
- Python 3.12
- `uv`
- LLM provider credentials

PostgreSQL is not required for the current file-backed runtime.

### Setup

```bash
git clone <repo-url> anchor_ui
cd anchor_ui
npm install
cd backend
uv python pin 3.12
uv sync
copy .env.example .env
cd ..
```

Edit `backend/.env` with one LLM provider configuration. For Azure OpenAI,
set `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`,
`AZURE_OPENAI_DEPLOYMENT`, and `DEFAULT_MODEL`.

No PostgreSQL setup is needed for the current file-backed runtime. No write API
key is needed for normal localhost use.

### Run

Start frontend and backend together:

```bash
npm run dev
```

Open:

```text
http://localhost:3000
```

Useful separate commands:

```bash
npm run dev:ui      # frontend only
npm run dev:agent   # backend only on http://localhost:8001
```

For a shared machine or public deployment, set `ANCHOR_WRITE_API_KEY` in
`backend/.env`, set `ALLOW_UNSAFE_LOCAL_WRITES=false`, and serve the backend
behind HTTPS/auth.
