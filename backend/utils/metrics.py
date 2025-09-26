from math import isfinite
from typing import Any, Dict


def clean_metrics(data: Dict[str, Any]) -> Dict[str, Any]:
    cleaned: Dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, float):
            cleaned[key] = value if isfinite(value) else None
        elif isinstance(value, dict):
            cleaned[key] = clean_metrics(value)
        else:
            cleaned[key] = value
    return cleaned
