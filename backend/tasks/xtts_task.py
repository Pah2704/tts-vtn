from __future__ import annotations

from typing import Dict

from celery import current_task, shared_task
from kombu.exceptions import OperationalError
from redis.exceptions import ConnectionError as RedisConnError

from backend.models.generate import GenerateRequest
from backend.modules.segmenter import SegmentationConfig, segment_text
from backend.modules.ssml_parser import Utterance, flatten_to_timeline
from backend.services.render_service import render_timeline_piper


def _progress(pct: int, meta: Dict | None = None) -> None:
    try:
        payload = {"progress": int(pct)}
        if meta:
            payload.update(meta)
        current_task.update_state(state="PROGRESS", meta=payload)
    except (OperationalError, RedisConnError, RuntimeError):  # backend missing/eager mode
        pass


@shared_task(bind=True)
def xtts_generate_task(self, payload: Dict) -> Dict:
    req = GenerateRequest(**payload)

    if req.textMode == "ssml":
        timeline = flatten_to_timeline(
            req.text,
            {"voiceId": req.voiceId, "speed": req.speed},
        )
    else:
        seg_cfg = SegmentationConfig(
            **(req.config.segmentation.model_dump(exclude_none=True) if req.config and req.config.segmentation else {})
        )
        parts = segment_text(req.text, seg_cfg)
        if not parts:
            parts = [req.text.strip()]
        timeline = [
            Utterance(
                voiceId=req.voiceId,
                text=part,
                speed=req.speed,
                breaksAfterMs=seg_cfg.autoBreakMs or 0,
            )
            for part in parts
        ]

    chunk_count = max(1, len(timeline))
    _progress(5, {"stage": "prepare", "chunks": chunk_count})

    overrides = req.config.dsp.model_dump(exclude_none=True) if req.config and req.config.dsp else None
    output_path, metadata = render_timeline_piper(
        timeline,
        preset_key=req.preset or "podcast_standard",
        dsp_overrides=overrides,
        export_ext=req.exportFormat or "wav",
    )

    _progress(95, {"stage": "finalize"})

    return {"ok": True, "url": f"/outputs/{output_path.name}", "meta": metadata}
