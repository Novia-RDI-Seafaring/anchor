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
```

```bash
cd backend
uv python pin 3.12
uv sync
copy .env.example .env
cd ..
```

Edit `backend/.env` with the model/API key values you need.

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
