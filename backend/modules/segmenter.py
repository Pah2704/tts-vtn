from __future__ import annotations

from typing import List, Optional
import re


class SegmentationConfig:
    def __init__(
        self,
        strategy: str = "punctuation",
        maxChunkChars: Optional[int] = None,
        mergeShortBelow: Optional[int] = None,
        autoBreakMs: Optional[int] = None,
    ) -> None:
        self.strategy = strategy
        self.maxChunkChars = maxChunkChars
        self.mergeShortBelow = mergeShortBelow
        self.autoBreakMs = autoBreakMs


_PUNCT_RE = re.compile(r"(?<=[\.!\?:;])\s+")


def segment_text(text: str, cfg: SegmentationConfig) -> List[str]:
    raw = (text or "").strip()
    if not raw:
        return []

    if cfg.strategy == "newline":
        parts = [p.strip() for p in raw.splitlines() if p.strip()]
    else:
        parts = [p.strip() for p in _PUNCT_RE.split(raw) if p.strip()]

    if cfg.mergeShortBelow and cfg.mergeShortBelow > 0:
        merged: List[str] = []
        buf = ""
        for part in parts:
            if len(part) < cfg.mergeShortBelow:
                buf = (buf + " " + part).strip() if buf else part
            else:
                if buf:
                    merged.append(buf)
                    buf = ""
                merged.append(part)
        if buf:
            merged.append(buf)
        parts = merged

    if cfg.maxChunkChars and cfg.maxChunkChars > 0:
        clamped: List[str] = []
        for part in parts:
            if len(part) <= cfg.maxChunkChars:
                clamped.append(part)
            else:
                segment = part
                while len(segment) > cfg.maxChunkChars:
                    cut = segment.rfind(" ", 0, cfg.maxChunkChars)
                    if cut <= 0:
                        cut = cfg.maxChunkChars
                    clamped.append(segment[:cut].strip())
                    segment = segment[cut:].strip()
                if segment:
                    clamped.append(segment)
        parts = clamped

    return parts
