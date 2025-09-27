from typing import Any, Dict, List

from fastapi import APIRouter

router = APIRouter()

DEFAULT_LUFS = -16

_DEFAULT_PRESET: Dict[str, Any] = {
    "id": "default",
    "name": "Default",
    "engine": "piper",
    "config": {},
    "export": {},
}


def _with_aliases(preset: Dict[str, Any]) -> Dict[str, Any]:
    """Merge legacy aliases (key/title/lufsTarget) with the current schema."""
    config = preset.get("config") or {}
    lufs = config.get("lufsTarget", preset.get("lufsTarget", DEFAULT_LUFS))
    return {
        **preset,
        "key": preset.get("id", preset.get("key")),
        "title": preset.get("name", preset.get("title")),
        "lufsTarget": lufs,
    }


def _load_presets() -> List[Dict[str, Any]]:
    # Stub implementation: return a single preset; replace with service call if available.
    return [_DEFAULT_PRESET]


@router.get("/api/presets")
@router.get("/api/config/presets")
def list_presets() -> List[Dict[str, Any]]:
    """Return preset list with backward-compatible aliases."""
    presets = _load_presets()

    if isinstance(presets, dict) and "presets" in presets:
        items: List[Dict[str, Any]] = []
        for preset_id, payload in (presets.get("presets") or {}).items():
            base: Dict[str, Any] = {"id": preset_id, **(payload or {})}
            if "name" not in base and "title" in base:
                base["name"] = base["title"]
            items.append(_with_aliases(base))
        return items

    return [_with_aliases(p) for p in (presets or [])]
