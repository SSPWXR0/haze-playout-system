from pathlib import Path
from . import ParseM3U, ParseXSFP


def parse_playlist_file(path: Path) -> list[dict]:
    suffix = path.suffix.lower()
    if suffix in {".m3u", ".m3u8"}:
        return ParseM3U.parse(path)
    if suffix == ".xspf":
        return ParseXSFP.parse(path)
    raise ValueError(f"Unsupported playlist format: {suffix}")