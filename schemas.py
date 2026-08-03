from datetime import datetime
from pydantic import BaseModel, AnyHttpUrl, Field
from typing import Any, Dict, List, Literal, Optional

PaginationType = Literal["auto", "none", "page", "offset", "cursor", "next_link"]

class PaginationConfig(BaseModel):
    type: PaginationType = Field(
        "auto",
        description="Pagination strategy: page, offset, cursor, next_link, none, or auto-detect.",
    )
    page_param: str = Field("page", description="Query parameter name for page numbers.")
    limit_param: str = Field("per_page", description="Query parameter name for page size.")
    limit: int = Field(100, description="Maximum number of records to ask for per request.")
    start_page: int = Field(1, description="Starting page number for page-based pagination.")
    cursor_param: str = Field("cursor", description="Query parameter name for cursor-based pagination.")
    next_link_path: Optional[str] = Field(
        None,
        description="JSON path to a next-page URL in the response, such as info.next.",
    )
    cursor_path: Optional[str] = Field(
        None,
        description="JSON path to a next cursor token in the response.",
    )
    max_pages: int = Field(20, description="Maximum pages to fetch for this source.")


class SourceConfig(BaseModel):
    name: str = Field(..., description="Friendly name for the source.")
    url: AnyHttpUrl = Field(..., description="The initial API endpoint to ingest.")
    auth: Optional[Dict[str, str]] = Field(None, description="Optional auth header or token information.")
    headers: Optional[Dict[str, str]] = Field(None, description="Optional extra HTTP headers.")
    params: Optional[Dict[str, Any]] = Field(None, description="Optional query parameters.")
    pagination: Optional[PaginationConfig] = Field(default_factory=PaginationConfig)
    data_path: Optional[str] = Field(
        None,
        description="Optional JSON path to the array of records in a wrapped response.",
    )
    max_records: Optional[int] = Field(
        None,
        description="Optional maximum number of records to ingest from this source.",
    )


class IngestRequest(BaseModel):
    sources: List[SourceConfig]


class IngestResponse(BaseModel):
    job_id: int
    status: str


class RecordResponse(BaseModel):
    id: int
    job_id: int
    source_name: str
    record_index: int
    payload: Dict[str, Any]
    persisted_at: datetime


class JobResponse(BaseModel):
    id: int
    source_name: str
    status: str
    started_at: datetime
    finished_at: Optional[datetime]
    pages_fetched: int
    records_stored: int
    error: Optional[str]
