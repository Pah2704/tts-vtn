from typing import Literal, TypedDict, Required, NotRequired

PresetKey = Literal["podcast_standard","audiobook_professional","announcement","natural_minimal"]

class CompParams(TypedDict, total=False):
    threshold: float       # dBFS
    ratio: float           # 2.0..4.0
    attack: float          # ms
    release: float         # ms
    makeup: float          # dB

class LevelMatch(TypedDict, total=False):
    enabled: bool
    per_utterance_target: float  # LUFS

class DspConfig(TypedDict):
    # bắt buộc
    lufs_target: Required[float]
    peak_ceiling: Required[float]
    # tuỳ chọn
    nr_strength: NotRequired[Literal["light","medium","strong"]]
    eq_profile: NotRequired[Literal["flat","voice_clarity","warmth","brightness"]]
    comp: NotRequired[CompParams]
    level_match: NotRequired[LevelMatch]

class PresetDef(TypedDict):
    key: Required[PresetKey]
    title: Required[str]
    dsp: Required[DspConfig]
    description: NotRequired[str]

PRESETS: dict[PresetKey, PresetDef] = {
    "podcast_standard": {
        "key": "podcast_standard", "title": "Podcast Standard",
        "description": "NR medium, clarity EQ, comp 3:1, -16 LUFS / -1 dBTP",
        "dsp": {
            "nr_strength": "medium", "eq_profile": "voice_clarity",
            "comp": {"threshold": -18, "ratio": 3.0, "attack": 12, "release": 120, "makeup": 0},
            "lufs_target": -16.0, "peak_ceiling": -1.0,
            "level_match": {"enabled": True, "per_utterance_target": -18.0},
        },
    },
    "audiobook_professional": {
        "key": "audiobook_professional", "title": "Audiobook Professional",
        "description": "NR light, warm EQ, soft comp, -18 LUFS",
        "dsp": {
            "nr_strength": "light", "eq_profile": "warmth",
            "comp": {"threshold": -20, "ratio": 2.5, "attack": 20, "release": 200, "makeup": 0},
            "lufs_target": -18.0, "peak_ceiling": -1.0,
            "level_match": {"enabled": True, "per_utterance_target": -19.0},
        },
    },
    "announcement": {
        "key": "announcement", "title": "Announcement",
        "description": "NR strong, bright EQ, tighter comp, -14 LUFS",
        "dsp": {
            "nr_strength": "strong", "eq_profile": "brightness",
            "comp": {"threshold": -16, "ratio": 4.0, "attack": 8, "release": 100, "makeup": 0},
            "lufs_target": -14.0, "peak_ceiling": -1.0,
            "level_match": {"enabled": False},
        },
    },
    "natural_minimal": {
        "key": "natural_minimal", "title": "Natural Minimal",
        "description": "NR light, flat EQ, minimal comp, -16 LUFS",
        "dsp": {
            "nr_strength": "light", "eq_profile": "flat",
            "comp": {"threshold": -24, "ratio": 1.5, "attack": 25, "release": 250, "makeup": 0},
            "lufs_target": -16.0, "peak_ceiling": -1.0,
            "level_match": {"enabled": False},
        },
    },
}
