from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .parsing import parse_playlist_file
from .config import HazeConfig

AUDIO_EXTENSIONS: frozenset[str] = frozenset({
    ".mp3", ".flac", ".wav", ".aac", ".ogg", ".opus",
    ".m4a", ".wma", ".aiff", ".alac", ".mp2", ".ape",
    ".wv", ".tta", ".ac3", ".dts",
})

PLAYLIST_EXTENSIONS: frozenset[str] = frozenset({
    ".m3u", ".m3u8", ".xspf",
})


@dataclass
class Track:
    path: Path
    title: Optional[str] = None
    duration: Optional[float] = None

    def __str__(self) -> str:
        return self.title or self.path.stem


@dataclass
class Playlist:
    name: str
    tracks: list[Track] = field(default_factory=list)
    transition: Optional[str] = None
    crossfade_duration: Optional[float] = None
    source_path: Optional[Path] = None

    def __len__(self) -> int:
        return len(self.tracks)

    def __iter__(self):
        return iter(self.tracks)

    def __bool__(self) -> bool:
        return bool(self.tracks)


def _tracks_from_dicts(raw: list[dict]) -> list[Track]:
    return [
        Track(
            path=entry["path"],
            title=entry.get("title"),
            duration=entry.get("duration"),
        )
        for entry in raw
    ]


def _scan_folder(directory: Path) -> list[Track]:
    return [
        Track(path=p.resolve())
        for p in sorted(directory.iterdir())
        if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS
    ]


def discover(cfg: HazeConfig) -> dict[str, Playlist]:
    playlists: dict[str, Playlist] = {}
    root = cfg.playlists_dir

    if not root.exists():
        return playlists

    default_transition = cfg.transitions.default
    default_crossfade = cfg.transitions.crossfade_duration

    root_tracks = _scan_folder(root)
    if root_tracks:
        playlists["Default"] = Playlist(
            name="Default",
            tracks=root_tracks,
            transition=default_transition,
            crossfade_duration=default_crossfade,
            source_path=root,
        )

    for entry in sorted(root.iterdir()):
        if entry.is_dir():
            tracks = _scan_folder(entry)
            if tracks:
                pl = Playlist(
                    name=entry.name,
                    tracks=tracks,
                    transition=default_transition,
                    crossfade_duration=default_crossfade,
                    source_path=entry,
                )
                playlists[pl.name] = pl

        elif entry.is_file() and entry.suffix.lower() in PLAYLIST_EXTENSIONS:
            try:
                raw = parse_playlist_file(entry)
            except Exception:
                continue
            tracks = _tracks_from_dicts(raw)
            if tracks:
                pl = Playlist(
                    name=entry.stem,
                    tracks=tracks,
                    transition=default_transition,
                    crossfade_duration=default_crossfade,
                    source_path=entry,
                )
                playlists[pl.name] = pl

    return playlists