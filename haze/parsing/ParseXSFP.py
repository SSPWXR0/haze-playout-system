import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional
from urllib.parse import unquote


_NS = "http://xspf.org/ns/0/"


def _resolve_location(location: str, base: Path) -> Path:
    if location.startswith("file:///"):
        return Path(unquote(location[8:]))
    if location.startswith("file://"):
        return Path(unquote(location[7:]))
    p = Path(unquote(location))
    if not p.is_absolute():
        p = base / p
    return p.resolve()


def parse(path: Path) -> list[dict]:
    tracks = []
    base = path.parent

    tree = ET.parse(path)
    root = tree.getroot()

    def _tag(name: str) -> str:
        return f"{{{_NS}}}{name}"

    for track_elem in root.iter(_tag("track")):
        location = track_elem.findtext(_tag("location"))
        title = track_elem.findtext(_tag("title"))
        duration_ms = track_elem.findtext(_tag("duration"))

        if not location:
            continue

        track_path = _resolve_location(location, base)

        duration: Optional[float] = None
        if duration_ms is not None:
            try:
                duration = float(duration_ms) / 1000.0
            except ValueError:
                pass

        if track_path.exists():
            tracks.append({
                "path": track_path,
                "title": title,
                "duration": duration,
            })

    return tracks