from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Dict
from xml.etree import ElementTree as ET
import re


@dataclass
class Utterance:
    voiceId: str
    text: str
    speed: float = 1.0
    preGainDb: float = 0.0
    breaksAfterMs: int = 0


WHITELIST_TAGS = {
    "speak",
    "voice",
    "prosody",
    "break",
    "emphasis",
    "say-as",
    "sub",
    "p",
    "s",
    "lang",
}
PROSODY_RATE_KEY = "rate"
VOICE_NAME_ATTR = "name"

SAFE_NODE_LIMIT = 2000
SAFE_MAX_DEPTH = 12
SAFE_MAX_TEXT = 20000

_RATE_MAP_KEYWORDS = {
    "x-slow": 0.7,
    "slow": 0.85,
    "medium": 1.0,
    "fast": 1.25,
    "x-fast": 1.5,
}


def _parse_rate_to_speed(val: str | None, base: float) -> float:
    if not val:
        return base
    v = val.strip().lower()
    if v.endswith("%"):
        try:
            pct = float(v[:-1])
            return max(0.5, min(2.0, base * (1.0 + pct / 100.0)))
        except ValueError:
            return base
    if v in _RATE_MAP_KEYWORDS:
        return _RATE_MAP_KEYWORDS[v]
    try:
        f = float(v)
        return max(0.5, min(2.0, f))
    except ValueError:
        return base


def _say_as_transform(kind: str, raw: str) -> str:
    s = raw.strip()
    kind = (kind or "").lower()
    if kind in {"digits", "characters", "spell-out"}:
        return " ".join(list(re.sub(r"\s+", " ", s))).strip()
    if kind == "number":
        return s
    if kind == "date":
        m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
        return f"{m.group(1)} {m.group(2)} {m.group(3)}" if m else s
    if kind == "time":
        m = re.match(r"^(\d{1,2}):(\d{2})$", s)
        return f"{m.group(1)} {m.group(2)}" if m else s
    return s


def _strip_unknown_tags(elem: ET.Element) -> None:
    for child in list(elem):
        if child.tag not in WHITELIST_TAGS:
            if child.tail:
                elem.text = (elem.text or "") + child.tail
            elem.remove(child)
        else:
            _strip_unknown_tags(child)


def _count_nodes(elem: ET.Element) -> int:
    return 1 + sum(_count_nodes(c) for c in elem)


def _max_depth(elem: ET.Element, cur: int = 1) -> int:
    return max([cur] + [_max_depth(c, cur + 1) for c in list(elem)])


def _collect_text(elem: ET.Element) -> str:
    parts: List[str] = []
    if elem.text:
        parts.append(elem.text)
    for child in elem:
        parts.append(_collect_text(child))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


def flatten_to_timeline(
    ssml: str,
    defaults: Dict[str, object] | None = None,
    *,
    validate: bool = True,
    stripUnknown: bool = True,
    errorMode: str = "warn",
) -> List[Utterance]:
    defaults = defaults or {}
    default_voice = str(defaults.get("voiceId", "en_GB-alan-medium"))
    default_speed = float(defaults.get("speed", 1.0))

    try:
        root = ET.fromstring(ssml)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid SSML XML: {exc}") from exc

    if root.tag != "speak":
        root = ET.fromstring(f"<speak>{ssml}</speak>")

    if stripUnknown:
        _strip_unknown_tags(root)

    if validate:
        node_count = _count_nodes(root)
        depth = _max_depth(root)
        total_text = len(_collect_text(root))
        if node_count > SAFE_NODE_LIMIT and errorMode == "fail":
            raise ValueError("SSML too many nodes")
        if depth > SAFE_MAX_DEPTH and errorMode == "fail":
            raise ValueError("SSML too deep")
        if total_text > SAFE_MAX_TEXT and errorMode == "fail":
            raise ValueError("SSML text too long")

    timeline: List[Utterance] = []
    cur_voice = default_voice
    cur_speed = default_speed
    pending_break_ms = 0

    def emit(text: str) -> None:
        nonlocal pending_break_ms
        content = text.strip()
        if not content:
            return
        timeline.append(
            Utterance(
                voiceId=cur_voice,
                text=content,
                speed=cur_speed,
                preGainDb=0.0,
                breaksAfterMs=pending_break_ms,
            )
        )
        pending_break_ms = 0

    def walk(elem: ET.Element) -> None:
        nonlocal cur_voice, cur_speed, pending_break_ms
        tag = elem.tag

        if tag == "voice":
            prev_voice = cur_voice
            cur_voice = elem.attrib.get(VOICE_NAME_ATTR, cur_voice)
            if elem.text:
                emit(elem.text)
            for child in list(elem):
                walk(child)
                if child.tail:
                    emit(child.tail)
            cur_voice = prev_voice
            return

        if tag == "prosody":
            prev_speed = cur_speed
            cur_speed = _parse_rate_to_speed(elem.attrib.get(PROSODY_RATE_KEY), cur_speed)
            if elem.text:
                emit(elem.text)
            for child in list(elem):
                walk(child)
                if child.tail:
                    emit(child.tail)
            cur_speed = prev_speed
            return

        if tag == "break":
            time_attr = (elem.attrib.get("time") or "").strip().lower()
            ms = 0
            if time_attr.endswith("ms"):
                try:
                    ms = int(float(time_attr[:-2]))
                except ValueError:
                    ms = 0
            elif time_attr.endswith("s"):
                try:
                    ms = int(float(time_attr[:-1]) * 1000)
                except ValueError:
                    ms = 0
            else:
                strength = (elem.attrib.get("strength") or "medium").lower()
                ms = {
                    "none": 0,
                    "x-weak": 80,
                    "weak": 160,
                    "medium": 240,
                    "strong": 360,
                    "x-strong": 500,
                }.get(strength, 240)
            if timeline:
                timeline[-1].breaksAfterMs += ms
            else:
                pending_break_ms += ms
            return

        if tag == "emphasis":
            for child in list(elem):
                walk(child)
                if child.tail:
                    emit(child.tail)
            return

        if tag == "say-as":
            kind = elem.attrib.get("interpret-as", "")
            text = _collect_text(elem)
            emit(_say_as_transform(kind, text))
            return

        if tag == "sub":
            alias = elem.attrib.get("alias", "")
            emit(alias or _collect_text(elem))
            return

        if tag in {"p", "s", "lang"}:
            if elem.text:
                emit(elem.text)
            for child in list(elem):
                walk(child)
                if child.tail:
                    emit(child.tail)
            return

        if tag == "speak":
            if elem.text:
                emit(elem.text)
            for child in list(elem):
                walk(child)
                if child.tail:
                    emit(child.tail)
            return

        if elem.text:
            emit(elem.text)
        for child in list(elem):
            walk(child)
            if child.tail:
                emit(child.tail)

    walk(root)
    return timeline
