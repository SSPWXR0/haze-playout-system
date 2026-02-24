from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml



@dataclass
class OutputSoundcardConfig:
    enabled: bool = True
    device: Optional[str] = None


@dataclass
class TransitionsConfig:
    default: str = "finish_track"
    crossfade_duration: float = 2.0


@dataclass
class PlayoutConfig:
    sample_rate: int = 48000
    channels: int = 2
    default_playlist: Optional[str] = None
    shuffle: bool = False
    shuffle_carry_over: int = 3


@dataclass
class WebConfig:
    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 8080


@dataclass
class HazeConfig:
    playout: PlayoutConfig = field(default_factory=PlayoutConfig)
    soundcard: OutputSoundcardConfig = field(default_factory=OutputSoundcardConfig)
    transitions: TransitionsConfig = field(default_factory=TransitionsConfig)
    web: WebConfig = field(default_factory=WebConfig)
    playlists_dir: Path = Path("Managed/Playlists")


def load(path: Path = Path("config.yaml")) -> HazeConfig:
    raw: dict = {}
    if path.exists():
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

    playout_raw = raw.get("playout", {})
    sc_raw = raw.get("outputs", {}).get("soundcard", {})
    trans_raw = raw.get("transitions", {})
    web_raw = raw.get("web", {})
    paths_raw = raw.get("paths", {})

    return HazeConfig(
        playout=PlayoutConfig(
            sample_rate=playout_raw.get("sample_rate", 48000),
            channels=playout_raw.get("channels", 2),
            default_playlist=playout_raw.get("default_playlist"),
            shuffle=playout_raw.get("shuffle", False),
            shuffle_carry_over=playout_raw.get("shuffle_carry_over", 3),
        ),
        soundcard=OutputSoundcardConfig(
            enabled=sc_raw.get("enabled", True),
            device=sc_raw.get("device"),
        ),
        transitions=TransitionsConfig(
            default=trans_raw.get("default", "finish_track"),
            crossfade_duration=trans_raw.get("crossfade_duration", 2.0),
        ),
        web=WebConfig(
            enabled=web_raw.get("enabled", True),
            host=web_raw.get("host", "0.0.0.0"),
            port=web_raw.get("port", 8080),
        ),
        playlists_dir=Path(paths_raw.get("playlists_dir", "Managed/Playlists")),
    )