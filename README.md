## Run Locally

### Backend

1. **Prerequisites**
   - Python 3.12+
   - PostgreSQL
   - LLM Provider (OpenAI, Anthropic, etc.)


2. Start PostgreSQL with pgvector (Docker)

We use the official pgvector image so no manual extension installation is required.

Option A — Quick Start (Single Command)

### Mac / Linux:
```
docker run -d \
  --name pgvector-db \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=admin123 \
  -e POSTGRES_DB=anchor \
  -p 5432:5432 \
  pgvector/pgvector:pg16
```

### Windows (PowerShell):

```
docker run -d --name pgvector-db -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=admin123 -e POSTGRES_DB=anchor -p 5432:5432 pgvector/pgvector:pg16
```

Enable the pgvector extension:

```
docker exec -it pgvector-db psql -U postgres -d anchor
```

Inside psql:

```
CREATE EXTENSION IF NOT EXISTS vector;
```

Exit:

```
\q
```


2. **Configuration**
   Create a `.env` file in the `backend/` directory:
   ```env
   PGVECTOR_HOST=localhost
   PGVECTOR_PORT=5432
   PGVECTOR_DB=anchor
   PGVECTOR_USER=postgres
   PGVECTOR_PASSWORD=admin123
   LLM_API_KEY=...
   LLM_MODEL=...
   ```

3. **Setup & Install**
   ```bash
   # Create virtual environment
   uv venv  # or: python -m venv venv

   # Activate
   # Windows:
   venv\Scripts\activate
   # Mac/Linux:
   # source venv/bin/activate

   # Install dependencies
   uv sync
   # OR for standard pip:
   pip install -e .
   ```

### Frontend

1. **Prerequisites**
   - Node.js

2. **Setup & Run**
   ```bash
   # Install dependencies
   npm install

   # Start development server
   npm run dev
   ```
