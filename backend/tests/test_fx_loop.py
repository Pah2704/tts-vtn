from typing import Any, cast
from backend.modules.fx_lib import loop_to_length
from pydub import AudioSegment

def test_loop_to_length_exact():
    seg = AudioSegment.silent(duration=250, frame_rate=16000)  # type: ignore[attr-defined]
    out = loop_to_length(seg, 1000)
    length_ms = int(len(cast(Any, out)))  # pydub: len(seg) => ms, cast để Pylance im
    assert abs(length_ms - 1000) <= 1
