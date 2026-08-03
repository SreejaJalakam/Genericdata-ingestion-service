# Design notes

## Goal
Build a generic ingestion service that can take one or more API endpoints and ingest records without being tied to a single schema or source.

## Architecture
- `app.py`: FastAPI web service with a lightweight UI and API endpoints for submitting ingestion jobs.
- `ingestion.py`: Generic ingestion engine with pluggable pagination strategies and record discovery.
- `db.py`: SQLite persistence layer using SQLAlchemy. Jobs and raw records are stored in separate tables.
- `schemas.py`: Pydantic models define the ingestion request shape and source configuration.
- `templates/index.html`: browser-friendly interface for entering source JSON and watching recent jobs.

## Generality and extensibility
- The ingestion engine does not require predefined columns. It discovers arrays of records in JSON responses and stores each record as raw JSON.
- Pagination support is separated from the HTTP fetch logic, so new pagination strategies can be added without rewriting the destination implementation.
- The persistence layer is intentionally simple: raw JSON payloads are stored in a database today, but any destination implementing the same interface can be added later (for example S3, Parquet, or a message queue).

## Public APIs chosen
- **Rick and Morty API**: Demonstrates paginated responses with a `next` link.
- **Public APIs directory**: Demonstrates a JSON wrapper response with a data field and no pagination.
- **Open Brewery DB**: Demonstrates page-based pagination with query parameters.

## Tradeoffs
- Raw JSON storage is flexible but less queryable than a fully normalized schema. This is intentional for a generic ingestion service, where schema discovery may happen downstream.
- The current implementation uses SQLite for simplicity. In a production service, a scalable destination like Postgres, ClickHouse, or object storage would be more appropriate.
- Pagination heuristics are intentionally conservative: auto-detection follows explicit next-link or cursor patterns and does not assume page-based behavior unless configured.

## What I would do with more time
- Add schema discovery and automatic schema creation for common record shapes.
- Add destination plugins for S3, Parquet streaming, and message queues.
- Add authentication helpers for common API patterns such as OAuth2 and API keys.
- Add retry/backoff for transient HTTP failures and better job monitoring.
- Add automated tests for ingestion, pagination, and UI interactions.

## Notes on AI assistance
This project was built with the help of an AI assistant (Antigravity). The AI accelerated the development of the boilerplate code for FastAPI, SQLAlchemy, and UI styling. 
One place the AI got something wrong: it initially assumed that the `data_path` parameter was nested inside the `pagination` object in the schema (e.g., `source.pagination.data_path`), which caused an `AttributeError` when ingesting non-paginated APIs (where `pagination` could be `None`). I caught this by running a test on the JSON Placeholder API, which lacks pagination, observed the exception in the terminal, and subsequently corrected the data model and ingestion logic to make `data_path` a top-level attribute on the `SourceConfig`.
