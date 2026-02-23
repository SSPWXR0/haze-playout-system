from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

ART_CACHE_PATH = Path("now_playing_art.jpg")


@dataclass
class TrackMetadata:
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    track_number: Optional[str] = None
    year: Optional[str] = None
    duration: Optional[float] = None
    art: Optional[bytes] = None
    art_mime: str = "image/jpeg"

    @property
    def display_title(self) -> str:
        if self.title and self.artist:
            return f"{self.artist} — {self.title}"
        return self.title or ""

    @property
    def has_art(self) -> bool:
        return bool(self.art)

    def save_art(self, path: Path = ART_CACHE_PATH):
        if self.art:
            try:
                path.write_bytes(self.art)
            except Exception as e:
                log.debug(f"Could not save art: {e}")
        else:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass

    def art_as_base64(self) -> Optional[str]:
        if not self.art:
            return None
        import base64
        return base64.b64encode(self.art).decode("ascii")

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "year": self.year,
            "track_number": self.track_number,
            "duration": self.duration,
            "has_art": self.has_art,
        }


def read(path: Path) -> TrackMetadata:
    try:
        from mutagen import File as MutagenFile
    except ImportError:
        log.warning("mutagen not installed — run: pip install mutagen")
        return TrackMetadata()

    try:
        f = MutagenFile(path, easy=False)
    except Exception as e:
        log.debug(f"mutagen could not read {path.name}: {e}")
        return TrackMetadata()

    if f is None:
        return TrackMetadata()

    meta = TrackMetadata()

    if f.info and hasattr(f.info, "length"):
        meta.duration = f.info.length

    suffix = path.suffix.lower()

    if suffix == ".mp3":
        _read_id3(f, meta)
    elif suffix == ".flac":
        _read_flac(f, meta)
    elif suffix in {".ogg", ".opus"}:
        _read_vorbis(f, meta)
    elif suffix in {".m4a", ".aac", ".alac", ".mp4"}:
        _read_mp4(f, meta)
    elif suffix == ".wma":
        _read_asf(f, meta)
    elif suffix in {".wav", ".aiff", ".aif"}:
        _read_id3(f, meta)
    else:
        _read_generic(f, meta)

    return meta


def _first(values) -> Optional[str]:
    if not values:
        return None
    v = values[0] if not isinstance(values, str) else values
    return str(v).strip() or None


def _read_id3(f, meta: TrackMetadata):
    tags = f.tags
    if tags is None:
        return
    if "TIT2" in tags:
        meta.title = str(tags["TIT2"]).strip() or None
    if "TPE1" in tags:
        meta.artist = str(tags["TPE1"]).strip() or None
    if "TALB" in tags:
        meta.album = str(tags["TALB"]).strip() or None
    if "TRCK" in tags:
        meta.track_number = str(tags["TRCK"]).strip() or None
    for year_tag in ("TDRC", "TDRL", "TYER"):
        if year_tag in tags:
            meta.year = str(tags[year_tag]).strip()[:4] or None
            break
    for key, frame in tags.items():
        if key.startswith("APIC"):
            meta.art = frame.data
            meta.art_mime = frame.mime or "image/jpeg"
            break


def _read_flac(f, meta: TrackMetadata):
    tags = f.tags
    if tags:
        meta.title = _first(tags.get("title"))
        meta.artist = _first(tags.get("artist"))
        meta.album = _first(tags.get("album"))
        meta.track_number = _first(tags.get("tracknumber"))
        meta.year = (_first(tags.get("date") or tags.get("year")) or "")[:4] or None
    if hasattr(f, "pictures") and f.pictures:
        pic = f.pictures[0]
        meta.art = pic.data
        meta.art_mime = pic.mime or "image/jpeg"


def _read_vorbis(f, meta: TrackMetadata):
    tags = f.tags
    if tags is None:
        return
    meta.title = _first(tags.get("title"))
    meta.artist = _first(tags.get("artist"))
    meta.album = _first(tags.get("album"))
    meta.track_number = _first(tags.get("tracknumber"))
    meta.year = (_first(tags.get("date") or tags.get("year")) or "")[:4] or None

    import base64
    from mutagen.flac import Picture
    for val in tags.get("metadata_block_picture", []):
        try:
            pic = Picture(base64.b64decode(val))
            meta.art = pic.data
            meta.art_mime = pic.mime or "image/jpeg"
            break
        except Exception:
            continue


def _read_mp4(f, meta: TrackMetadata):
    tags = f.tags
    if tags is None:
        return
    meta.title = _first(tags.get("\xa9nam"))
    meta.artist = _first(tags.get("\xa9ART"))
    meta.album = _first(tags.get("\xa9alb"))
    meta.year = (_first(tags.get("\xa9day")) or "")[:4] or None
    trkn = tags.get("trkn")
    if trkn:
        try:
            meta.track_number = str(trkn[0][0])
        except Exception:
            pass
    covr = tags.get("covr")
    if covr:
        from mutagen.mp4 import MP4Cover
        cover = covr[0]
        meta.art = bytes(cover)
        meta.art_mime = "image/png" if cover.imageformat == MP4Cover.FORMAT_PNG else "image/jpeg"


def _read_asf(f, meta: TrackMetadata):
    tags = f.tags
    if tags is None:
        return
    meta.title = _first(tags.get("Title"))
    meta.artist = _first(tags.get("Author"))
    meta.album = _first(tags.get("WM/AlbumTitle"))
    meta.year = (_first(tags.get("WM/Year")) or "")[:4] or None
    meta.track_number = _first(tags.get("WM/TrackNumber"))
    wm_pic = tags.get("WM/Picture")
    if wm_pic:
        raw = wm_pic[0].value
        try:
            mime_end = raw.index(b"\x00", 1)
            mime = raw[1:mime_end].decode("utf-8", errors="ignore")
            data_start = raw.index(b"\x00", mime_end + 1) + 1
            meta.art = raw[data_start:]
            meta.art_mime = mime or "image/jpeg"
        except Exception:
            pass


def _read_generic(f, meta: TrackMetadata):
    tags = f.tags
    if tags is None:
        return
    if hasattr(tags, "as_dict"):
        tags = tags.as_dict()
    if isinstance(tags, dict):
        meta.title = _first(tags.get("title") or tags.get("TIT2"))
        meta.artist = _first(tags.get("artist") or tags.get("TPE1"))
        meta.album = _first(tags.get("album") or tags.get("TALB"))