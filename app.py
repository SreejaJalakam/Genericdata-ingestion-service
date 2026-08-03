from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import List

from fastapi import BackgroundTasks, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from db import Job, SessionLocal, init_db
from ingestion import ingest_source
from schemas import IngestRequest, IngestResponse, SourceConfig

app = FastAPI(title="Generic Data Ingestion Service")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.on_event("startup")
def startup_event() -> None:
    init_db()


def get_job(session: Session, job_id: int) -> Job:
    return session.query(Job).filter(Job.id == job_id).first()


@app.get("/", response_class=HTMLResponse)
def root(request: Request) -> HTMLResponse:
    with SessionLocal() as session:
        jobs = session.query(Job).order_by(Job.id.desc()).limit(10).all()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "jobs": jobs,
        },
    )


@app.post("/ingest", response_model=IngestResponse)
def ingest(request_data: IngestRequest, background_tasks: BackgroundTasks) -> IngestResponse:
    if not request_data.sources:
        raise ValueError("At least one source configuration is required.")

    with SessionLocal() as session:
        job_names = ", ".join(source.name for source in request_data.sources)
        job_urls = ", ".join(str(source.url) for source in request_data.sources)
        job = Job(
            source_name=job_names,
            status="pending",
            started_at=datetime.utcnow(),
            source_url=job_urls,
        )
        session.add(job)
        session.commit()
        session.refresh(job)

    background_tasks.add_task(_run_job, job.id, request_data.sources)
    return IngestResponse(job_id=job.id, status=job.status)


@app.post("/submit", response_class=RedirectResponse)
def submit(sources_json: str = Form(...), background_tasks: BackgroundTasks = None) -> RedirectResponse:
    import json
    from fastapi import HTTPException

    try:
        payload = json.loads(sources_json)
        request_data = IngestRequest(sources=payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {exc}")

    with SessionLocal() as session:
        job_names = ", ".join(source.name for source in request_data.sources)
        job_urls = ", ".join(str(source.url) for source in request_data.sources)
        job = Job(
            source_name=job_names,
            status="pending",
            started_at=datetime.utcnow(),
            source_url=job_urls,
        )
        session.add(job)
        session.commit()
        session.refresh(job)

    if background_tasks is not None:
        background_tasks.add_task(_run_job, job.id, request_data.sources)
    else:
        _run_job(job.id, request_data.sources)

    return RedirectResponse(url="/", status_code=303)


def _run_job(job_id: int, sources: List[SourceConfig]) -> None:
    with SessionLocal() as session:
        job = get_job(session, job_id)
        if job is None:
            return
        job.status = "running"
        job.started_at = datetime.utcnow()
        session.commit()

    aggregate_pages = 0
    aggregate_records = 0
    errors = []
    max_workers = min(4, len(sources))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(ingest_source, job_id, source): source for source in sources
        }
        for future in as_completed(future_map):
            source = future_map[future]
            try:
                result = future.result()
                aggregate_pages += result["pages_fetched"]
                aggregate_records += result["records_stored"]
            except Exception as exc:
                errors.append(f"{source.name}: {exc}")

    with SessionLocal() as session:
        job = get_job(session, job_id)
        if not job:
            return
        job.pages_fetched = aggregate_pages
        job.records_stored = aggregate_records
        job.finished_at = datetime.utcnow()
        if errors:
            job.status = "failed"
            job.error = " | ".join(errors)
        else:
            job.status = "completed"
        session.commit()


@app.get("/jobs/{job_id}")
def job_details(job_id: int):
    with SessionLocal() as session:
        job = get_job(session, job_id)
        if job is None:
            return {"error": "Job not found"}
        return {
            "id": job.id,
            "source_name": job.source_name,
            "status": job.status,
            "started_at": job.started_at.isoformat(),
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            "pages_fetched": job.pages_fetched,
            "records_stored": job.records_stored,
            "error": job.error,
        }
