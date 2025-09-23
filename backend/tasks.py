# backend/tasks.py
from __future__ import annotations
from typing import Dict, Any
from .celery_app import celery_app

# (tuỳ chọn) nếu cần sleep mô phỏng: from time import sleep

@celery_app.task(bind=True, name="generate_task")
def generate_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Bước 2: chỉ cập nhật progress. Logic parse/tts/dsp/mix/qc/export sẽ được bổ sung ở Bước 3–5.
    """
    def report(pct: int):
        # Chỉ gửi %; schema /status hiện tại không có "stage"
        self.update_state(state="PROGRESS", meta={"progress": int(pct)})

    # parse
    report(5)
    # tts
    report(30)
    # dsp
    report(55)
    # mix
    report(70)
    # qc
    report(85)
    # export
    report(95)

    # Trả stub để /result có shape hợp lệ khi job SUCCESS (khi chạy thật)
    return {
        "audio_url": "/outputs/dummy.wav",  # Bước 3 sẽ ghi file thật và trả URL đúng
        "format": "wav",
        "metrics": {
            "lufsIntegrated": -16.0,
            "truePeakDb": -1.0,
            "durationSec": 1.0,
        },
    }
