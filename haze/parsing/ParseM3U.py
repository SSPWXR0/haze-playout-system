from pathlib import Path
from typing import Optional


def parse(path: Path) -> list[dict]:
    tracks = []
    base = path.parent
    current_title: Optional[str] = None
    current_duration: Optional[float] = None

    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()

            if not line or line.startswith("#EXTM3U"):
                continue

            if line.startswith("#EXTINF:"):
                rest = line[8:]
                parts = rest.split(",", 1)
                try:
                    current_duration = float(parts[0].split()[0])
                except (ValueError, IndexError):
                    current_duration = None
                current_title = parts[1].strip() if len(parts) > 1 else None
                continue

            if line.startswith("#"):
                continue

            track_path = Path(line)
            if not track_path.is_absolute():
                track_path = base / track_path

            track_path = track_path.resolve()

            if track_path.exists():
                tracks.append({
                    "path": track_path,
                    "title": current_title,
                    "duration": current_duration,
                })

            current_title = None
            current_duration = None

    return tracks