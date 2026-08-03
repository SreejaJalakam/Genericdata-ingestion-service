import os
from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text, create_engine
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

Base = declarative_base()

DB_URL = os.getenv("INGEST_DB_URL", "sqlite:///./data_ingestion.db")
ENGINE = create_engine(DB_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=ENGINE, expire_on_commit=False)


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    source_name = Column(String(200), nullable=False)
    status = Column(String(50), nullable=False, default="pending")
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at = Column(DateTime, nullable=True)
    pages_fetched = Column(Integer, default=0, nullable=False)
    records_stored = Column(Integer, default=0, nullable=False)
    error = Column(Text, nullable=True)
    source_url = Column(String(1000), nullable=False)

    records = relationship("Record", back_populates="job", cascade="all, delete")


class Record(Base):
    __tablename__ = "records"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    source_name = Column(String(200), nullable=False)
    source_url = Column(String(1000), nullable=False)
    record_index = Column(Integer, nullable=False)
    payload = Column(JSON, nullable=False)
    persisted_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    job = relationship("Job", back_populates="records")


class FailedRecord(Base):
    """Dead Letter Queue for records that couldn't be persisted/parsed."""
    __tablename__ = "failed_records"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True)
    source_name = Column(String(200), nullable=True)
    source_url = Column(String(1000), nullable=True)
    payload = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    persisted_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class SourceState(Base):
    """Store per-source state like last_cursor or last_updated watermark for incremental syncs."""
    __tablename__ = "source_state"

    id = Column(Integer, primary_key=True, index=True)
    source_key = Column(String(1000), unique=True, nullable=False)
    last_cursor = Column(String(2000), nullable=True)
    last_updated_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


def init_db() -> None:
    Base.metadata.create_all(bind=ENGINE)
