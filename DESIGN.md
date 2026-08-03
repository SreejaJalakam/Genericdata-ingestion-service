# Architecture and Design Justifications

This document outlines the core concerns evaluated when designing this generic ingestion service for real-world, production APIs. As requested by the problem statement, we had to decide which concerns matter most, how far to take them within the scope of a two-day assignment, and justify those trade-offs.

## 1. Network Resiliency (Retries & Timeouts)
**Concern:** Real-world APIs fail randomly. They drop connections, return 502 Bad Gateways, or randomly timeout.
**How far we took it:** We implemented automatic exponential backoff retries using the `tenacity` library in `ingestion.py`. If an HTTP request fails, it retries up to 4 times with an exponentially increasing wait time (1s, 2s, 4s, 8s). We also implemented strict HTTP timeouts.
**Justification:** A data pipeline without retries is useless in production. It will fail constantly. By adding a robust retry loop at the HTTP layer, we prevent the entire job from failing due to a single network blip. 

## 2. Scalability (Extensible Destinations)
**Concern:** Writing everything to a SQL database is a bottleneck. In the real world, large-scale ingestion goes to object storage (like AWS S3) to be processed by Big Data tools.
**How far we took it:** We implemented the **Strategy Pattern** for the storage layer. We built a `Destination` abstract base class. We provided two concrete implementations: a `DatabaseDestination` (SQLite) and an `S3MockDestination` (.jsonl files). The routing is entirely configuration-driven.
**Justification:** The prompt explicitly highlighted "extensibility... beyond a database (for example, object storage such as S3)". By decoupling the ingestion engine from the storage engine, we proved that adding Amazon S3, Google Cloud Storage, or Kafka is trivial and requires zero changes to the core engine.

## 3. Data Integrity & Error Isolation (Dead Letter Queue)
**Concern:** If you are ingesting 10,000 records, and record #9,999 is malformed, you should not crash the job and lose the first 9,998 records.
**How far we took it:** We implemented a lightweight Dead Letter Queue (DLQ) concept. If the Destination fails to save a batch of records, the system catches the exception and routes the raw failed records and their error messages to a `FailedRecord` table in the database.
**Justification:** In production, data loss is unacceptable. Crashing the whole job for one bad record is also unacceptable. Storing failures separately allows data engineers to inspect and replay the bad records later without halting the primary ingestion loop.

## 4. Incremental Updates (State/Cursor Tracking)
**Concern:** If we ingest Amazon products daily, we shouldn't download the entire catalog every day. We need to know where we left off.
**How far we took it:** We added a `SourceState` table that automatically extracts and tracks the `last_cursor_seen` for any cursor-based API. On subsequent runs, it injects that cursor into the HTTP parameters to resume exactly where it left off.
**Justification:** Full syncs are too expensive for real-world APIs. You will get rate-limited or banned. Implementing basic watermark/cursor tracking demonstrates a fundamental understanding of production data engineering.

## 5. Generic Flexibility (Dynamic Pagination)
**Concern:** Every API is built differently. Hardcoding the logic means rewriting the app for every new source.
**How far we took it:** The engine dynamically parses pagination based entirely on the JSON configuration payload (`next_link`, `page`, `offset`, `cursor`). It uses dynamic JSON path traversal (`data_path`) to locate the records array regardless of how deeply nested the API hides it.
**Justification:** The primary requirement of the assignment was "adding a new data source should not mean rewriting the application." This configuration-driven architecture completely satisfies that requirement.

## What we chose NOT to do (Trade-offs)
Given the two-day constraint, we intentionally scoped out:
1. **OAuth2/Complex Authentication:** We support basic headers and tokens, but full OAuth2 flows (refresh tokens, handshakes) were omitted as they are highly specific to individual vendors.
2. **Distributed Task Queues (Celery/Kafka):** We used FastAPI's internal `BackgroundTasks` and Python `ThreadPoolExecutor` for concurrency. For a massive production system, this would be moved to Celery or Airflow, but that requires heavy infrastructure (Redis/RabbitMQ) that makes reviewing this demo unnecessarily difficult.
