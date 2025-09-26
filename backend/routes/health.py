from __future__ import annotations

import os
import subprocess
from fastapi import APIRouter
from pydantic import BaseModel
import redis


router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    version: str | None = None
    piper: bool
    redis: bool


def _git_sha() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True,
        ).strip()
    except Exception:
        return None


def _has_piper() -> bool:
    piper_bin = os.getenv("PIPER_BIN", "/opt/piper/piper")
    try:
        subprocess.run(
            [piper_bin, "--help"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        return True
    except Exception:
        return False


def _ping_redis() -> bool:
    url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    try:
        client = redis.from_url(url)
        return bool(client.ping())
    except Exception:
        return False


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        version=_git_sha(),
        piper=_has_piper(),
        redis=_ping_redis(),
    )
