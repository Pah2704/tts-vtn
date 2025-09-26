from __future__ import annotations

from typing import List, Sequence
import numpy as np


def _ensure_2d(x: np.ndarray) -> np.ndarray:
    if x.ndim == 1:
        return x[:, None]
    return x


def _crossfade(a: np.ndarray, b: np.ndarray, fade_samples: int) -> np.ndarray:
    if fade_samples <= 0:
        return np.vstack((a, b))
    fade_samples = min(fade_samples, len(a), len(b))
    head = a[:-fade_samples]
    tail_a = a[-fade_samples:]
    head_b = b[fade_samples:]
    tail_b = b[:fade_samples]
    ramp_out = np.linspace(1.0, 0.0, fade_samples, endpoint=False)[:, None]
    ramp_in = 1.0 - ramp_out
    mixed = tail_a * ramp_out + tail_b * ramp_in
    return np.vstack((head, mixed, head_b))


def assemble_linear_pcm(
    chunks: Sequence[np.ndarray],
    sr: int,
    breaks_after_ms: Sequence[int] | None = None,
    *,
    crossfade_ms: int = 10,
) -> np.ndarray:
    if not chunks:
        return np.zeros((0, 1), dtype=np.float32)
    first = _ensure_2d(np.asarray(chunks[0], dtype=np.float32))
    ch = first.shape[1]
    out = first
    fade_samples = int(sr * crossfade_ms / 1000.0)

    breaks_after_ms = breaks_after_ms or [0] * len(chunks)
    for idx in range(1, len(chunks)):
        gap_ms = int(breaks_after_ms[idx - 1]) if idx - 1 < len(breaks_after_ms) else 0
        if gap_ms > 0:
            gap = np.zeros((int(sr * gap_ms / 1000.0), ch), dtype=np.float32)
            out = np.vstack((out, gap))
        nxt = _ensure_2d(np.asarray(chunks[idx], dtype=np.float32))
        if nxt.shape[1] != ch:
            if nxt.shape[1] == 1 and ch > 1:
                nxt = np.repeat(nxt, ch, axis=1)
            else:
                nxt = nxt[:, :ch]
        out = _crossfade(out, nxt, fade_samples)
    return out
