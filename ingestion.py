import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import httpx

from db import Record, SessionLocal
from schemas import PaginationConfig, SourceConfig

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


def _choose_next_url(response_json: Any, pagination: PaginationConfig, last_url: str, params: Dict[str, Any]) -> Optional[Tuple[str, Dict[str, Any]]]:
    if pagination.type == "none":
        return None

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


def _fetch_json(url: str, headers: Dict[str, str], params: Dict[str, Any], timeout: int = 20) -> Any:
    with httpx.Client(timeout=timeout) as client:
        response = client.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()


def _store_records(job_id: int, source_name: str, source_url: str, records: List[Any], start_index: int = 0) -> int:
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


def ingest_source(job_id: int, source: SourceConfig) -> Dict[str, Any]:
    headers: Dict[str, str] = dict(source.headers or {})
    if source.auth:
        headers.update(source.auth)

    params: Dict[str, Any] = dict(source.params or {})
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
    while total_pages < max_pages:
        state = (current_url, tuple(sorted((k, str(v)) for k, v in current_params.items())))
        if state in visited_states:
            break
        visited_states.add(state)

        try:
            response_json = _fetch_json(current_url, headers, current_params)
        except Exception as exc:
            raise RuntimeError(f"Failed fetching {current_url}: {exc}") from exc

        path = source.data_path if source.data_path else getattr(source.pagination, "data_path", None) if source.pagination else None
        records = _discover_records(response_json, path)
        if not records:
            break
        if source.max_records is not None and total_records + len(records) > source.max_records:
            records = records[: max(0, source.max_records - total_records)]

        stored = _store_records(job_id, source.name, current_url, records, start_index=total_records)
        total_records += stored
        total_pages += 1

        if source.max_records is not None and total_records >= source.max_records:
            break

        next_page = _choose_next_url(response_json, source.pagination or PaginationConfig(), current_url, current_params)
        if not next_page:
            break
        current_url, current_params = next_page

    return {"pages_fetched": total_pages, "records_stored": total_records}

    return {"pages_fetched": total_pages, "records_stored": total_records}
