# System Architecture & Design Decisions

This document is not a tutorial on how to run the application (see `README.md`). Instead, it answers the fundamental engineering question: **Why did I design it this way?**

Treating these endpoints as real, external production APIs required several strict architectural trade-offs, which are detailed below.

## Configuration-Driven Architecture
**Why:** The assignment explicitly stated that adding a new data source must not mean rewriting the application.
**Implementation:** The entire engine is blind to the domain it is ingesting. It relies on a JSON configuration payload (`SourceConfig`) to dynamically dictate HTTP parameters, header authentication, data paths, and pagination bounds. Hardcoding `if api == "rick_and_morty"` is an anti-pattern; instead, the engine evaluates mathematical bounds based on the supplied configuration.

## Pagination Abstraction
**Why:** APIs handle pagination wildly differently. Some use URL parameters (`page=2`), some use offsets (`offset=100`), some use cursors, and others use `next` link strings inside the payload or HTTP headers.
**Implementation:** We abstracted pagination into a standard schema. The ingestion engine parses this schema and dynamically calculates the next request loop. It supports auto-detection fallback if the API natively returns pagination metadata.

## Destination Abstraction
**Why:** Modern data engineering pipelines rarely dump massive payloads directly into a relational SQL database. They dump raw data into a Data Lake (e.g., AWS S3).
**Implementation:** We utilized the **Strategy Pattern** via a `Destination` abstract base class. We provided two concrete implementations: `DatabaseDestination` (SQLite) and `S3MockDestination` (saving raw `.jsonl` files). This proves that you can swap destinations in the configuration without altering a single line of backend parsing logic.

## Retry Strategy
**Why:** Real-world APIs fail randomly (502 Bad Gateway, 504 Gateway Timeout, connection drops).
**Implementation:** We wrapped the HTTP fetching logic using the `tenacity` Python library. It automatically handles exponential backoff (e.g., waiting 1s, 2s, 4s, 8s) for failed HTTP requests. This prevents a 1-second network blip from crashing a 10,000-record ingestion job.

## Validation
**Why:** Garbage in, garbage out. If a user defines an invalid pagination path, the engine must catch it.
**Implementation:** We leveraged `pydantic` schemas for strict structural validation of incoming configurations. The API will reject malformed configurations (e.g., missing URLs) before the background worker is ever spawned.

## Checkpointing (Incremental Syncs)
**Why:** When scraping a large e-commerce catalog, we shouldn't download the entire catalog every day. We need to know where we left off.
**Implementation:** The system tracks the `last_cursor_seen` for cursor-based APIs in a `SourceState` table. Upon subsequent executions, it injects this cursor back into the request parameters to resume precisely where it ended previously.

## Idempotency (Planned)
**Why:** Re-running a failed job should not duplicate data in the destination.
**Planned implementation:** While out-of-scope for the two-day constraint, the next immediate production feature is generating a stable `SHA-256` hash for every JSON record upon ingestion, using that hash as a primary key constraint to prevent duplicate rows during manual re-runs.

## Job Tracking
**Why:** Background ingestion jobs can run for hours. Engineers need operational visibility.
**Implementation:** We persist jobs to a SQL database with states (`pending`, `running`, `completed`, `failed`), tracking pages fetched and records stored. A lightweight web UI polls the backend via AJAX to render live status updates.

## Trade-offs
Due to the two-day constraint, we explicitly deferred:
- **OAuth2:** Supported basic token headers, but full OAuth2 flows (refresh tokens) are highly specific and time-consuming to mock.
- **Distributed Queues:** Used Python's local `ThreadPoolExecutor` for concurrency. For true high-throughput scraping, this should be moved to Celery or Airflow.

## Production Evolution
If scaling this service to scrape Amazon/Walmart at enterprise volumes, we would evolve the current stack:
- **Storage:** SQLite → PostgreSQL (or Snowflake).
- **Compute:** ThreadPoolExecutor → Celery Workers backed by Redis.
- **Data Lake:** Mock S3 (`.jsonl` files) → Real AWS S3 via `boto3`.
- **Security:** Static Headers → dynamic AWS SigV4 / HashiCorp Vault integrations.
