from abc import ABC, abstractmethod
from typing import List, Any

from db import Record, FailedRecord, SessionLocal


class Destination(ABC):
    @abstractmethod
    def save_records(self, job_id: int, source_name: str, source_url: str, records: List[Any], start_index: int = 0) -> int:
        """Persist a list of records. Returns number of records stored."""


class DatabaseDestination(Destination):
    def save_records(self, job_id: int, source_name: str, source_url: str, records: List[Any], start_index: int = 0) -> int:
        with SessionLocal() as session:
            for offset, record in enumerate(records, start=1):
                try:
                    session.add(
                        Record(
                            job_id=job_id,
                            source_name=source_name,
                            source_url=source_url,
                            record_index=start_index + offset,
                            payload=record,
                        )
                    )
                except Exception as exc:
                    # On failure to persist a single record, move it to DLQ
                    session.add(
                        FailedRecord(
                            job_id=job_id,
                            source_name=source_name,
                            source_url=source_url,
                            payload=record,
                            error=str(exc),
                        )
                    )
            session.commit()
            return len(records)


# Placeholder S3Destination for future extension. Avoid importing boto3 unless used.
class S3Destination(Destination):
    def __init__(self, bucket_name: str, prefix: str = ""):
        self.bucket_name = bucket_name
        self.prefix = prefix
        # boto3 client will be created lazily to avoid adding dependency unless used
        self._client = None

    def _get_client(self):
        if self._client is None:
            import boto3
            self._client = boto3.client("s3")
        return self._client

    def save_records(self, job_id: int, source_name: str, source_url: str, records: List[Any], start_index: int = 0) -> int:
        # Simple implementation: write a JSON lines file to S3 per batch
        import json
        client = self._get_client()
        key = f"{self.prefix}job-{job_id}/{source_name.replace(' ', '_')}-{start_index}.jsonl"
        body = "\n".join(json.dumps(r) for r in records)
        client.put_object(Bucket=self.bucket_name, Key=key, Body=body.encode("utf-8"))
        return len(records)
