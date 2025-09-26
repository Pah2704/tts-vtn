# backend/api/routes.py
from typing import List, Literal, Optional, Dict, Any

from urllib.parse import urljoin

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from celery.result import AsyncResult

from backend.modules.presets import PRESETS

ExportFormat = Literal["mp3", "wav", "flac", "m4a"]
PresetKey = Literal["podcast_standard", "audiobook_professional", "announcement", "natural_minimal"]


class QualityMetrics(BaseModel):
    lufsIntegrated: float
    truePeakDb: float
    durationSec: float
    rms: Optional[float] = None
    crestFactor: Optional[float] = None
    snrApprox: Optional[float] = None
    clippingCount: Optional[int] = None
    silenceGapsMs: Optional[List[int]] = None
    qualityScore: Optional[int] = None
    warnings: Optional[List[str]] = None


class SyncGenerateResponse(BaseModel):
    mode: Literal["sync"] = "sync"
    engine: str
    url: str
    filename: str
    format: ExportFormat
    metrics: QualityMetrics
    duration: Optional[float] = None


JobState = Literal["queued", "processing", "done", "error"]


class ErrorInfo(BaseModel):
    code: str
    message: str


class JobStatusResponse(BaseModel):
    jobId: str
    state: JobState
    progress: Optional[int] = None
    error: Optional[ErrorInfo] = None
    result: Optional[SyncGenerateResponse] = None


class PresetInfo(BaseModel):
    key: PresetKey
    title: str
    lufsTarget: float
    description: Optional[str] = None


api_router = APIRouter(tags=["tts"])


def _map_state(celery_state: str) -> JobState:
    state = (celery_state or "").upper()
    if state in {"PENDING", "RECEIVED", "REVOKED"}:
        return "queued"
    if state in {"STARTED", "PROGRESS", "RETRY"}:
        return "processing"
    if state == "SUCCESS":
        return "done"
    if state == "FAILURE":
        return "error"
    return "processing"


def _build_sync_response(payload: Dict[str, Any], request: Optional[Request] = None) -> SyncGenerateResponse:
    audio_url = payload.get("audio_url")
    if not isinstance(audio_url, str):
        raise HTTPException(status_code=500, detail="Malformed worker result: 'audio_url' must be str")

    if request is not None:
        audio_url = urljoin(str(request.base_url), audio_url.lstrip("/"))

    fmt_raw = payload.get("format")
    fmt: ExportFormat = fmt_raw if fmt_raw in {"mp3", "wav", "flac", "m4a"} else "wav"

    metrics_raw = payload.get("metrics") or {}
    if not isinstance(metrics_raw, dict):
        raise HTTPException(status_code=500, detail="Malformed worker result: 'metrics' must be object")

    metrics = QualityMetrics(**metrics_raw)
    filename = payload.get("filename")
    if not isinstance(filename, str):
        filename = audio_url.rsplit("/", 1)[-1]

    engine = payload.get("engine", "piper")

    return SyncGenerateResponse(
        engine=engine,
        url=audio_url,
        filename=filename,
        format=fmt,
        metrics=metrics,
        duration=metrics.durationSec,
    )


@api_router.get("/status/{job_id}", response_model=JobStatusResponse)
async def get_status(job_id: str, request: Request) -> JobStatusResponse:
    result = AsyncResult(job_id)
    mapped = _map_state(result.state)
    meta: Dict[str, Any] = result.info if isinstance(result.info, dict) else {}
    progress_raw = meta.get("progress")
    progress = int(progress_raw) if isinstance(progress_raw, (int, float)) else None

    if mapped == "error":
        detail = str(meta) if meta else "Unknown error"
        return JobStatusResponse(
            jobId=job_id,
            state=mapped,
            progress=progress,
            error=ErrorInfo(code="WORKER_ERROR", message=detail),
        )

    if mapped == "done" and isinstance(result.result, dict):
        try:
            sync_payload = _build_sync_response(result.result, request)
        except HTTPException:
            sync_payload = None
        else:
            return JobStatusResponse(jobId=job_id, state=mapped, progress=progress or 100, result=sync_payload)

    return JobStatusResponse(jobId=job_id, state=mapped, progress=progress)


@api_router.get("/result/{job_id}", response_model=SyncGenerateResponse)
async def get_result(job_id: str, request: Request) -> SyncGenerateResponse:
    result = AsyncResult(job_id)
    if result.state != "SUCCESS":
        raise HTTPException(status_code=404, detail="Result not ready")

    payload: Dict[str, Any] = result.result or {}
    return _build_sync_response(payload, request)


@api_router.get("/presets", response_model=List[PresetInfo])
def list_presets() -> List[PresetInfo]:
    return [
        PresetInfo(
            key=preset["key"],
            title=preset["title"],
            lufsTarget=preset["dsp"]["lufs_target"],
            description=preset.get("description", ""),
        )
        for preset in PRESETS.values()
    ]
