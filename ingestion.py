import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from db import SessionLocal, FailedRecord, SourceState
from schemas import PaginationConfig, SourceConfig
from destinations import DatabaseDestination, Destination

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def _json_path(data: Any, path: str) -> Optional[Any]:
    if not path:
        return None
    node = data
    for part in path.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return None
    return node


def _discover_records(data: Any, configured_path: Optional[str] = None) -> List[Any]:
    if configured_path:
        node = _json_path(data, configured_path)
        if isinstance(node, list):
            return node
        if node is None:
            return []

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        candidates = []
        for key, value in data.items():
            if isinstance(value, list):
                candidates.append((key, len(value), value))
        if candidates:
            _, _, records = max(candidates, key=lambda item: item[1])
            return records

    return [data]


def _headers_next_link(response: httpx.Response) -> Optional[str]:
    # Common header patterns: Link: <url>; rel="next" or X-Next-Page
    link = response.headers.get("Link")
    if link:
        # parse simple Link header
        parts = [p.strip() for p in link.split(",")]
        for part in parts:
            if 'rel="next"' in part or "rel=\"next\"" in part:
                # extract between < and >
                start = part.find("<")
                end = part.find(">", start)
                if start != -1 and end != -1:
                    return part[start + 1 : end]
    xnext = response.headers.get("X-Next-Page") or response.headers.get("X-Next-Url")
    if xnext:
        return xnext
    return None


def _choose_next_url(response_json: Any, pagination: PaginationConfig, last_url: str, params: Dict[str, Any], response_obj: Optional[httpx.Response] = None) -> Optional[Tuple[str, Dict[str, Any]]]:
    if pagination.type == "none":
        return None

    # Header-based next link (common in some APIs)
    if response_obj is not None:
        next_from_headers = _headers_next_link(response_obj)
        if next_from_headers:
            return next_from_headers, {}

    if pagination.type in ("auto", "next_link"):
        next_path = pagination.next_link_path or "info.next"
        next_value = _json_path(response_json, next_path)
        if isinstance(next_value, str) and next_value:
            return next_value, {}

    if pagination.type in ("auto", "cursor"):
        cursor = _json_path(response_json, pagination.cursor_path or "next_cursor")
        if isinstance(cursor, str) and cursor:
            next_params = dict(params)
            next_params[pagination.cursor_param] = cursor
            next_params[pagination.limit_param] = pagination.limit
            return last_url, next_params

    if pagination.type == "page":
        page = int(params.get(pagination.page_param, pagination.start_page))
        next_page = page + 1
        next_params = dict(params)
        next_params[pagination.page_param] = next_page
        next_params[pagination.limit_param] = pagination.limit
        return last_url, next_params

    if pagination.type == "offset":
        offset = int(params.get("offset", 0))
        next_params = dict(params)
        next_params["offset"] = offset + pagination.limit
        next_params[pagination.limit_param] = pagination.limit
        return last_url, next_params

    if pagination.type == "cursor":
        cursor = _json_path(response_json, pagination.cursor_path or "next_cursor")
        if isinstance(cursor, str) and cursor:
            next_params = dict(params)
            next_params[pagination.cursor_param] = cursor
            next_params[pagination.limit_param] = pagination.limit
            return last_url, next_params

    return None


@retry(reraise=True, stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=1, max=10), retry=retry_if_exception_type(httpx.HTTPError))
def _fetch_json(url: str, headers: Dict[str, str], params: Dict[str, Any], timeout: int = 20) -> Tuple[Any, httpx.Response]:
    with httpx.Client(timeout=timeout) as client:
        response = client.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json(), response


def ingest_source(job_id: int, source: SourceConfig, destination: Optional[Destination] = None) -> Dict[str, Any]:
    """Ingest a single source into the provided destination. By default uses DatabaseDestination."""
    if destination is None:
        destination = DatabaseDestination()

    headers: Dict[str, str] = dict(source.headers or {})
    if source.auth:
        headers.update(source.auth)

    # Check for per-source stored state (watermark/cursor) and inject into params
    params: Dict[str, Any] = dict(source.params or {})
    state_key = getattr(source, "state_key", None) or str(source.url)
    with SessionLocal() as session:
        state = session.query(SourceState).filter(SourceState.source_key == state_key).first()
        if state and state.last_cursor:
            # inject cursor into params if the source expects a cursor param
            if source.pagination and source.pagination.type in ("cursor", "auto") and source.pagination.cursor_param:
                params[source.pagination.cursor_param] = state.last_cursor

    if source.pagination and source.pagination.type == "page":
        params.setdefault(source.pagination.page_param, source.pagination.start_page)
        params.setdefault(source.pagination.limit_param, source.pagination.limit)
    elif source.pagination and source.pagination.type == "offset":
        params.setdefault("offset", 0)
        params.setdefault(source.pagination.limit_param, source.pagination.limit)
    elif source.pagination and source.pagination.type == "cursor":
        params.setdefault(source.pagination.cursor_param, None)
        params.setdefault(source.pagination.limit_param, source.pagination.limit)

    total_records = 0
    total_pages = 0
    visited_states = set()
    current_url = str(source.url)
    current_params = dict(params)
    max_pages = source.pagination.max_pages if source.pagination else 20

    last_cursor_seen = None
    while total_pages < max_pages:
        state = (current_url, tuple(sorted((k, str(v)) for k, v in current_params.items())))
        if state in visited_states:
            break
        visited_states.add(state)

        try:
            response_json, response_obj = _fetch_json(current_url, headers, current_params)
        except Exception as exc:
            # Save error on job-level failed record and abort this source gracefully
            with SessionLocal() as session:
                session.add(FailedRecord(job_id=job_id, source_name=source.name, source_url=current_url, payload=None, error=str(exc)))
                session.commit()
            raise RuntimeError(f"Failed fetching {current_url}: {exc}") from exc

        path = source.data_path if source.data_path else getattr(source.pagination, "data_path", None) if source.pagination else None
        records = _discover_records(response_json, path)
        if not records:
            break
        if source.max_records is not None and total_records + len(records) > source.max_records:
            records = records[: max(0, source.max_records - total_records)]

        # Persist via destination plugin
        try:
            stored = destination.save_records(job_id, source.name, current_url, records, start_index=total_records)
        except Exception as exc:
            # If destination fails, write all records to DLQ individually
            with SessionLocal() as session:
                for r in records:
                    session.add(FailedRecord(job_id=job_id, source_name=source.name, source_url=current_url, payload=r, error=str(exc)))
                session.commit()
            stored = 0

        total_records += stored
        total_pages += 1

        # Extract cursor if available for watermarking
        if source.pagination and source.pagination.type in ("cursor", "auto") and source.pagination.cursor_path:
            cursor = _json_path(response_json, source.pagination.cursor_path)
            if isinstance(cursor, str) and cursor:
                last_cursor_seen = cursor

        if source.max_records is not None and total_records >= source.max_records:
            break

        next_page = _choose_next_url(response_json, source.pagination or PaginationConfig(), current_url, current_params, response_obj)
        if not next_page:
            break
        current_url, current_params = next_page

    # persist observed state (cursor) for incremental syncs
    if last_cursor_seen:
        with SessionLocal() as session:
            state = session.query(SourceState).filter(SourceState.source_key == state_key).first()
            if not state:
                state = SourceState(source_key=state_key, last_cursor=last_cursor_seen, updated_at=datetime.utcnow())
                session.add(state)
            else:
                state.last_cursor = last_cursor_seen
                state.updated_at = datetime.utcnow()
            session.commit()

    return {"pages_fetched": total_pages, "records_stored": total_records}