from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


app = FastAPI(title="Parqcel Cloud API", version="0.1.0")


class FeaturizeRequest(BaseModel):
    input_path: str = Field(..., description="Local path to input CSV/Parquet")
    output_path: str = Field(..., description="Local output path for parquet features")
    mode: Literal["async", "inline"] = "async"


class PcaRequest(BaseModel):
    input_path: str = Field(..., description="Local path to input CSV/Parquet")
    output_path: str = Field(..., description="Local output path for PCA CSV")
    components: int = 2
    mode: Literal["async", "inline"] = "async"


class JobStatus(BaseModel):
    job_id: str
    operation: str
    status: Literal["queued", "running", "succeeded", "failed"]
    created_at: str
    updated_at: str
    detail: str | None = None


_jobs: dict[str, JobStatus] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/jobs/featurize", response_model=JobStatus)
def create_featurize_job(req: FeaturizeRequest) -> JobStatus:
    from cloud.worker import run_featurize

    job_id = str(uuid.uuid4())
    job = JobStatus(
        job_id=job_id,
        operation="featurize",
        status="queued",
        created_at=_now(),
        updated_at=_now(),
    )
    _jobs[job_id] = job

    if req.mode == "inline":
        job.status = "running"
        job.updated_at = _now()
        try:
            run_featurize(req.input_path, req.output_path)
            job.status = "succeeded"
            job.updated_at = _now()
        except Exception as exc:
            job.status = "failed"
            job.updated_at = _now()
            job.detail = str(exc)

    return job


@app.post("/v1/jobs/pca", response_model=JobStatus)
def create_pca_job(req: PcaRequest) -> JobStatus:
    from cloud.worker import run_pca

    job_id = str(uuid.uuid4())
    job = JobStatus(
        job_id=job_id,
        operation="pca",
        status="queued",
        created_at=_now(),
        updated_at=_now(),
    )
    _jobs[job_id] = job

    if req.mode == "inline":
        job.status = "running"
        job.updated_at = _now()
        try:
            run_pca(req.input_path, req.output_path, req.components)
            job.status = "succeeded"
            job.updated_at = _now()
        except Exception as exc:
            job.status = "failed"
            job.updated_at = _now()
            job.detail = str(exc)

    return job


@app.get("/v1/jobs/{job_id}", response_model=JobStatus)
def get_job(job_id: str) -> JobStatus:
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job
