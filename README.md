# Generic Data Ingestion Service

A Python-based generic ingestion service built with FastAPI, SQLAlchemy, and HTTPX.

## What this project does
- Accepts one or more public API endpoints as input.
- Discovers records in JSON responses without being hardcoded to a single schema.
- Supports multiple pagination styles (`next` links, page numbers, offset parameters, and auto-detected pagination).
- Persists raw API records in a SQLite database for later analysis.
- Includes a simple web UI for submitting ingestion jobs and inspecting completed jobs.

## Public APIs used for demo
- `https://rickandmortyapi.com/api/character` — paginated API using `info.next`.
- `https://api.publicapis.org/entries` — non-paginated JSON wrapper with `entries` records.
- `https://api.openbrewerydb.org/breweries` — page-based pagination with `page` and `per_page`.

## Run locally
1. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   .\.venv\Scripts\activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Start the app:
   ```bash
   uvicorn app:app --reload
   ```
4. Open `http://127.0.0.1:8000` in your browser.

Optionally set `INGEST_DB_URL` before starting the app to store ingested records in a different destination, for example:

```bash
set INGEST_DB_URL=sqlite:///./data_ingestion.db
```

## If you prefer Docker
```bash
docker compose up --build
```

## How to use
- Enter a JSON array of source configurations in the web UI.
- Each source may include:
  - `name`: user-friendly name
  - `url`: API endpoint to ingest
  - `headers`, `params`, `auth`
  - `pagination`: optional pagination strategy
- Start ingestion and watch job status update.

## Architecture and design decisions
- **Generic ingestion layer:** The service does not require a prebuilt schema. It finds the first suitable record array in each JSON response and stores records as raw JSON.
- **Extensible destination model:** Records are stored in a database today, but the ingestion engine is separated from persistence so future destinations like S3 or a data lake can be added easily.
- **Pagination support:** Supports both page-based and next-link style APIs. A best-effort auto-detection mode works when pagination fields are present in the response.
- **Real-world API resiliency:** The code logs request failures, supports configurable headers/auth, and limits pages fetched to avoid runaway jobs.
- **Lightweight UI:** A small interactive page demonstrates the service and allows non-technical reviewers to exercise ingestion without writing code.

## Notes on AI assistance
This project was developed with AI tooling to accelerate implementation (e.g., scaffolding the FastAPI boilerplate, writing the Jinja templates). 

**Where the AI got it wrong:** Early on, the AI assumed that all paginated APIs return `next` links in the JSON response body. I realized that some enterprise APIs (like GitHub) actually return pagination links hidden inside the HTTP Headers (e.g., `Link: <url>; rel="next"`). I caught this during testing, rejected the AI's naive implementation, and explicitly instructed it to write a parser that checks `response.headers` for `rel="next"` links before falling back to the JSON body. You can see this logic in `ingestion.py -> _headers_next_link()`.

## Architecture, Trade-offs, & Future Work
To address the prompt's core question—identifying which concerns matter in real-world ingestion, deciding how far to take them, and what to do with more time—I have documented all architectural decisions, trade-offs, and a future production roadmap in the **[FUTURE_WORK.md](./FUTURE_WORK.md)** file.
