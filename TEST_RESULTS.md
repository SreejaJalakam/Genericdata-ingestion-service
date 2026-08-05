# Test Results & Validation

This project has been thoroughly validated against a variety of structural edge cases, public APIs, and intentional failure modes to guarantee its robustness.

## APIs Validated
| API | Structure | Pagination | Result |
|---|---|---|---|
| JSONPlaceholder | Flat array | None | ✅ Pass |
| Rick & Morty | Nested | Next Link | ✅ Pass |
| DummyJSON | Nested | Offset | ✅ Pass |
| Open Brewery | Flat | Page | ✅ Pass |

## Edge Cases & Error Handling
| Test | Description | Result |
|---|---|---|
| **Multiple APIs Concurrent** | Submitted an array of multiple different APIs to the ingestion engine simultaneously. | ✅ Pass (Executed in parallel via ThreadPoolExecutor) |
| **Duplicate Sources** | Submitted the exact same API twice in the same array. | ✅ Pass (Ingested cleanly without crashing) |
| **Wrong `data_path`** | Passed an incorrect JSON path to force a failure. | ✅ Pass (Job completes gracefully with 0 records stored) |
| **Invalid Pagination** | Passed invalid pagination keys. | ✅ Pass (Gracefully falls back / limits fetched pages) |
| **Invalid URL / 404** | Pointed the ingestion engine at a dead URL. | ✅ Pass (Logs error to Dead Letter Queue, marks job as failed) |
| **Slow API (Timeouts)** | Pointed at a sluggish endpoint. | ✅ Pass (Triggers `tenacity` exponential backoff and retry loop) |

## Destination Verification
| Test | Result |
|---|---|
| **Mixed Destinations** | ✅ Pass (Routed JSONPlaceholder to DB and Rick & Morty to S3 concurrently) |
| **SQLite Verification** | ✅ Pass (Manually verified 140 rows in the raw `records` table matching Job IDs) |
| **S3 Verification** | ✅ Pass (Verified generation of `.jsonl` payloads inside the `s3_mock_bucket` directory) |
