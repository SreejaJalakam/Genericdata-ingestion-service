import abc
import json
import os
from typing import Any, List

from db import Record, SessionLocal


class Destination(abc.ABC):
    """Abstract base class for all data destinations."""
    @abc.abstractmethod
    def store_records(
        self, job_id: int, source_name: str, source_url: str, records: List[Any], start_index: int = 0
    ) -> int:
        pass


class DatabaseDestination(Destination):
    """Stores raw JSON records in the primary SQLite database."""
    def store_records(
        self, job_id: int, source_name: str, source_url: str, records: List[Any], start_index: int = 0
    ) -> int:
        with SessionLocal() as session:
            for offset, record in enumerate(records, start=1):
                session.add(
                    Record(
                        job_id=job_id,
                        source_name=source_name,
                        source_url=source_url,
                        record_index=start_index + offset,
                        payload=record,
                    )
                )
            session.commit()
            return len(records)


class S3MockDestination(Destination):
    """Simulates storing data to S3 by writing JSONL files to a local directory."""
    def __init__(self, bucket_dir: str = "./s3_mock_bucket"):
        self.bucket_dir = bucket_dir
        os.makedirs(self.bucket_dir, exist_ok=True)

    def store_records(
        self, job_id: int, source_name: str, source_url: str, records: List[Any], start_index: int = 0
    ) -> int:
        safe_name = "".join(c if c.isalnum() else "_" for c in source_name)
        filename = os.path.join(self.bucket_dir, f"{safe_name}_job_{job_id}.jsonl")
        
        with open(filename, "a", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")
        return len(records)


def get_destination(name: str) -> Destination:
    if name == "s3":
        return S3MockDestination()
    return DatabaseDestination()
