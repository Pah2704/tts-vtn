import numpy as np

from backend.modules.assembler import assemble_linear_pcm


def sine(sr: int, dur_s: float, freq: float = 440.0) -> np.ndarray:
    t = np.arange(int(sr * dur_s)) / sr
    return (0.2 * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def test_assemble_with_break_and_crossfade() -> None:
    sr = 24_000
    a = sine(sr, 0.5)
    b = sine(sr, 0.5, freq=660.0)
    out = assemble_linear_pcm([a, b], sr, breaks_after_ms=[250, 0], crossfade_ms=10)
    expected_len = int(sr * (0.5 + 0.25 + 0.5) - sr * 0.010)
    assert abs(len(out) - expected_len) < sr * 0.02
