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
2. Install backend dependencies: `pip install -r app/requirements.txt` (inside your virtual environment).
3. Start the API locally: `uvicorn app.main:app --reload --port 8000`.
4. In another terminal install UI deps (`pip install -r ui/requirements.txt`) and launch the Streamlit UI: `streamlit run ui/app.py`.
5. Ingest the raw corpus into SQLite/FAISS once the server is up:
   `curl -X POST http://127.0.0.1:8000/admin/ingest -H "X-Admin-Token: <token>"`.

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

## Feedback

- Every assistant response in the Streamlit UI now has a “Feedback” box where you can mark the answer as Helpful/Not helpful and optionally leave a comment.
- Feedback is sent to the backend via `POST /feedback` and stored in `data/logs/events.db` as `event_type="user_feedback"`.
- To inspect recent feedback entries:
  ```
  sqlite3 data/logs/events.db "select event_type, payload_json from events where event_type='user_feedback' order by id desc limit 5;"
  ```

## Grounded Chat Responses

- `/chat` retrieves the top chunks, builds a context block, and calls the configured OpenAI chat model with the Mortgage Agent system prompt.
- The assistant must cite only retrieved sources using `[S#]` references and output the required sections (Answer, Key points, optional Next steps/Citations/Disclaimer).
- After the LLM responds, grounding enforcement validates that only allowed citations are used and that citations exist when `CITATIONS_REQUIRED=true`. Violations (and missing API keys or model failures) trigger a safe fallback response with no citation payload.
- Each request logs `chat_request`, `retrieval_completed`, `llm_completed`, and `chat_response` events so you can audit retrieval, generation, and policy enforcement outcomes.

## Canada.ca Corpus Fetcher

Use the helper script to pull approved Canada.ca pages into `data/corpus/raw/` before ingestion:

```bash
python3 scripts/fetch_urls_to_txt.py --urls-file data/corpus/seed_urls/fcac_pack1.json
curl -X POST http://127.0.0.1:8000/admin/ingest -H "X-Admin-Token: <token>"
```

The script normalizes URLs (fixing `htmlz` typos), extracts the `<main>` content, and writes deterministic filenames such as `canadaca__down-payment__CA__YYYY-MM-DD.txt`.
Extraction strips common navigation/boilerplate blocks (Related links, Report a problem, Date modified, etc.) so only the main guidance content remains.

## Corpus Packs

Fetch additional packs and rebuild the index:

```bash
python3 scripts/fetch_urls_to_txt.py --urls-file data/corpus/seed_urls/cmhc_consumer_guidance.json
python3 scripts/fetch_urls_to_txt.py --urls-file data/corpus/seed_urls/osfi_stress_test.json
python3 scripts/fetch_urls_to_txt.py --urls-file data/corpus/seed_urls/cra_fthb_programs.json
curl -X POST http://127.0.0.1:8000/admin/ingest -H "X-Admin-Token: <token>"
```
For frequently changing sources (OSFI, CRA program details), re-fetch these packs at least weekly before re-ingesting.

## Deploying to Render (API)

1. Connect this repository to Render and select the `render.yaml` blueprint. Render will detect the `mortgage-agent-api` service definition and build using the Dockerfile.
2. Provision environment variables in the Render dashboard (all `sync: false` entries in `render.yaml` must be set manually):
   - `OPENAI_API_KEY`
   - `ADMIN_TOKEN`
   - Optional overrides: `LLM_MODEL`, `EMBEDDING_MODEL`, `STRICT_GROUNDING`, `CITATIONS_REQUIRED`
3. The service automatically mounts a persistent `/data` disk (FAISS index, corpus, and SQLite logs are stored there). No ingestion runs automatically on startup—trigger `/admin/ingest` after you upload corpus files.
4. After deploy, verify the API with `curl https://<your-service>.onrender.com/health`.
5. On a fresh Render disk, populate the corpus and ingest with one command:
   ```
   curl -X POST https://<your-service>.onrender.com/admin/fetch_and_ingest -H "X-Admin-Token: <token>"
   ```
   (Running `/admin/ingest` alone will return 0 docs until the corpus is fetched.)

## Deploying the Streamlit UI

1. Connect the repo to Streamlit Community Cloud and select `ui/app.py` as the entrypoint.
2. In Streamlit “Secrets”, add:
   ```
   API_BASE_URL = "https://<your-render-service>.onrender.com"
   PUBLIC_UI = "true"
   ```
   Add `OPENAI_API_KEY` only if the UI will call the OpenAI API directly (not required today).
3. Set the run command to `streamlit run ui/app.py` (default).
4. When the UI loads, it will detect `PUBLIC_UI` and hide admin/debug controls.

## Post-deploy Smoke Test

1. Visit `https://<your-render-service>.onrender.com/health` and ensure the JSON shows `status: "ok"`.
2. From your laptop, upload/refresh corpus packs and POST `/admin/ingest` with the admin token:
   `curl -X POST https://<your-render-service>.onrender.com/admin/ingest -H "X-Admin-Token: <token>"`.
3. Open the Streamlit UI (either locally or on Streamlit Cloud) and ask a question such as “What is the OSFI stress test for uninsured mortgages?”—confirm you get an answer plus citations.
4. When refreshing the corpus on Render, rerun the fetch + ingest endpoint and re-ask a question to confirm the new content is available.

## Environment Configuration

See `.env.example` for all variables. Example commands:

```bash
cp .env.example .env
```

Key settings for grounded responses:

- `LLM_MODEL`, `LLM_TEMPERATURE`, `LLM_MAX_OUTPUT_TOKENS` – controls the chat completion API.
- `STRICT_GROUNDING`, `CITATIONS_REQUIRED` – toggles grounding enforcement behavior.
