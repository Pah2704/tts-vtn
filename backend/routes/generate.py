from __future__ import annotations

from typing import Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from urllib.parse import urljoin

from backend.models.generate import GenerateRequest
from backend.modules.ssml_parser import flatten_to_timeline, Utterance
from backend.modules.segmenter import segment_text, SegmentationConfig
from backend.services.render_service import render_timeline_piper
from backend.utils.metrics import clean_metrics

try:
    from backend.tasks.xtts_task import xtts_generate_task
except Exception:  # pragma: no cover - optional dependency
    xtts_generate_task = None  # type: ignore

router = APIRouter()


class GenerateSyncResponse(BaseModel):
    engine: str
    mode: Literal["sync"] = "sync"
    url: str
    filename: str
    format: Optional[str] = None
    duration: Optional[float] = None
    metrics: Optional[Dict] = None


class GenerateAsyncResponse(BaseModel):
    engine: str
    mode: Literal["async"] = "async"
    jobId: str


def _build_timeline(req: GenerateRequest) -> List[Utterance]:
    if req.textMode == "ssml":
        ssml_cfg = req.config.ssml if req.config and req.config.ssml else None
        timeline = flatten_to_timeline(
            req.text,
            {"voiceId": req.voiceId, "speed": req.speed},
            validate=ssml_cfg.validate_ if ssml_cfg is not None else True,
            stripUnknown=ssml_cfg.stripUnknown if ssml_cfg and ssml_cfg.stripUnknown is not None else True,
            errorMode=ssml_cfg.errorMode if ssml_cfg and ssml_cfg.errorMode else "warn",
        )
        return timeline

    seg_cfg = SegmentationConfig(**(req.config.segmentation.model_dump(exclude_none=True) if req.config and req.config.segmentation else {}))
    parts = segment_text(req.text, seg_cfg)
    if not parts:
        parts = [req.text.strip()]
    break_ms = seg_cfg.autoBreakMs or 0
    return [
        Utterance(
            voiceId=req.voiceId,
            text=part,
            speed=req.speed,
            breaksAfterMs=break_ms,
        )
        for part in parts
    ]


@router.post("/api/generate", response_model=GenerateSyncResponse | GenerateAsyncResponse)
def generate(req: GenerateRequest, request: Request) -> GenerateSyncResponse | GenerateAsyncResponse:
    if req.engine == "piper":
        timeline = _build_timeline(req)
        if not timeline:
            raise HTTPException(status_code=422, detail={"code": "empty_timeline", "message": "No content to synthesize"})

        dsp_overrides = req.config.dsp.model_dump(exclude_none=True) if req.config and req.config.dsp else None
        export_format = req.exportFormat or "wav"
        out_path, metadata = render_timeline_piper(
            timeline,
            preset_key=req.preset or "podcast_standard",
            dsp_overrides=dsp_overrides,
            export_ext=export_format,
        )
        metrics = clean_metrics(metadata.get("metrics") or {})
        rel_name = out_path.name
        file_url = urljoin(str(request.base_url), f"outputs/{rel_name}")
        return GenerateSyncResponse(
            engine="piper",
            url=file_url,
            filename=rel_name,
            format=export_format,
            duration=metadata.get("duration"),
            metrics=metrics,
        )

    if req.engine == "xtts":
        if xtts_generate_task is None:
            raise HTTPException(status_code=503, detail={"code": "xtts_unavailable", "message": "XTTS task not configured"})
        payload = req.model_dump(mode="json", exclude_none=True)
        job = xtts_generate_task.delay(payload)
        return GenerateAsyncResponse(engine="xtts", jobId=job.id)

    raise HTTPException(status_code=400, detail={"code": "bad_engine", "message": "Unsupported engine"})
