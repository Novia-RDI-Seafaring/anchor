## Run Locally

### Backend

1. **Prerequisites**
   - Python 3.12+
   - PostgreSQL
   - LLM Provider (OpenAI, Anthropic, etc.)

2. **Configuration**
   Create a `.env` file in the `backend/` directory:
   ```env
   DATABASE_URL=...
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
