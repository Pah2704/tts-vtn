from __future__ import annotations

import json
import mimetypes
import os
from urllib.parse import urljoin
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

router = APIRouter()

OUTPUTS_DIR = Path(os.getenv("OUTPUTS_DIR", "/app/backend/outputs"))
AUDIO_EXT = {".wav", ".mp3", ".flac", ".m4a", ".ogg"}


class HistoryItem(BaseModel):
    filename: str
    url: Optional[str]
    missing: bool = False
    createdAt: str
    sizeBytes: int
    engine: Optional[str] = None
    preset: Optional[str] = None
    duration: Optional[float] = None
    format: Optional[str] = None


def _sidecar(path: Path) -> dict | None:
    meta_path = path.with_suffix(path.suffix + ".meta.json")
    if meta_path.exists():
        try:
            return json.loads(meta_path.read_text("utf-8"))
        except Exception:
            return None
    return None


@router.get("/history", response_model=list[HistoryItem])
def history(request: Request, limit: int = Query(10, ge=1, le=100)) -> list[HistoryItem]:
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    files = [p for p in OUTPUTS_DIR.glob("*") if p.is_file() and p.suffix.lower() in AUDIO_EXT]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    items: list[HistoryItem] = []
    for path in files[:limit]:
        stat = path.stat()
        meta = _sidecar(path) or {}
        created = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
        mime, _ = mimetypes.guess_type(path.name)
        fmt = (mime or "").split("/")[-1]
        if not fmt:
            fmt = path.suffix.lstrip(".")
        exists = path.exists()
        abs_url = None
        if exists and request is not None:
            abs_url = urljoin(str(request.base_url), f"outputs/{path.name}")
        elif exists:
            abs_url = f"/outputs/{path.name}"
        items.append(
            HistoryItem(
                filename=path.name,
                url=abs_url,
                missing=not exists,
                createdAt=created,
                sizeBytes=stat.st_size,
                engine=meta.get("engine"),
                preset=meta.get("preset"),
                duration=meta.get("duration"),
                format=fmt,
            )
        )
    return items
