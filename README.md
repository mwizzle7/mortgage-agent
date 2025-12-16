# Mortgage Agent

Conversational Mortgage Agent for Canadian home buyers with Retrieval-Augmented Generation (RAG), logging, and guardrails per PRD.

## Repository Structure

- `app/` – application source (UI, orchestrator, services)
- `data/corpus/raw/` – curated mortgage corpus inputs
- `data/indexes/faiss/` – local vector index outputs
- `data/logs/` – structured logs/analytics tables
- `PRD_Mortgage_Agent.md` – full product requirements document

## Local Runtime

1. Copy `.env.example` to `.env` and fill in secrets/configuration.
2. Install dependencies: `pip install -r app/requirements.txt` (inside your virtual environment).
3. Start the API locally: `uvicorn app.main:app --reload --port 8000`.
4. Ingest the raw corpus into SQLite/FAISS once the server is up:
   `curl -X POST http://127.0.0.1:8000/admin/ingest`.

## Test UI

Start the FastAPI service:
```
uvicorn app.main:app --reload --port 8000
```

Launch the Streamlit UI:
```
streamlit run ui/app.py
```

Streamlit prints the access URL after boot (by default http://localhost:8501).

## Grounded Chat Responses

- `/chat` retrieves the top chunks, builds a context block, and calls the configured OpenAI chat model with the Mortgage Agent system prompt.
- The assistant must cite only retrieved chunks using `[C#]` references and output the required sections (Answer, Key points, optional Next steps/Citations/Disclaimer).
- After the LLM responds, grounding enforcement validates that only allowed citations are used and that citations exist when `CITATIONS_REQUIRED=true`. Violations (and missing API keys or model failures) trigger a safe fallback response with no citation payload.
- Each request logs `chat_request`, `retrieval_completed`, `llm_completed`, and `chat_response` events so you can audit retrieval, generation, and policy enforcement outcomes.

## Canada.ca Corpus Fetcher

Use the helper script to pull approved Canada.ca pages into `data/corpus/raw/` before ingestion:

```bash
python scripts/fetch_canadaca_to_txt.py
curl -X POST http://127.0.0.1:8000/admin/ingest
```

The script normalizes URLs (fixing `htmlz` typos), extracts the `<main>` content, and writes deterministic filenames such as `canadaca__down-payment__CA__YYYY-MM-DD.txt`.

## Environment Configuration

See `.env.example` for all variables. Example commands:

```bash
cp .env.example .env
```

Key settings for grounded responses:

- `LLM_MODEL`, `LLM_TEMPERATURE`, `LLM_MAX_OUTPUT_TOKENS` – controls the chat completion API.
- `STRICT_GROUNDING`, `CITATIONS_REQUIRED` – toggles grounding enforcement behavior.
