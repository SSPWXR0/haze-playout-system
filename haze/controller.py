from __future__ import annotations

import logging
import queue
import subprocess
import threading
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from .config import HazeConfig
from .metadata import TrackMetadata, read as read_metadata
from .playlist import Playlist, Track, discover
from .shuffle import ShuffleDeck

if TYPE_CHECKING:
    from .webserver import WebServer
    from .mpegts_meta import MetadataInjector

log = logging.getLogger(__name__)

CHUNK_FRAMES = 4096


class State(Enum):
    STOPPED = auto()
    PLAYING = auto()
    PAUSED = auto()


class Controller:
    def __init__(self, cfg: HazeConfig):
        self.cfg = cfg
        self.state = State.STOPPED

        self.playlists: dict[str, Playlist] = {}
        self.active_playlist: Optional[Playlist] = None
        self._pending_playlist: Optional[Playlist] = None
        self._track_index: int = 0
        self._shuffle: bool = cfg.playout.shuffle
        self._deck: Optional[ShuffleDeck] = None
        self.current_meta: TrackMetadata = TrackMetadata()

        self._audio_queue: queue.Queue[Optional[bytes]] = queue.Queue(maxsize=32)
        self._stop_decode = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._track_end_event = threading.Event()

        self._decode_thread: Optional[threading.Thread] = None
        self._ffmpeg_udp: Optional[subprocess.Popen] = None
        self._sd_stream = None
        self._udp_feed_thread: Optional[threading.Thread] = None

        self._webserver: Optional[WebServer] = None
        self._meta_injector: Optional[MetadataInjector] = None
        self._tui: Optional[object] = None

        self._lock = threading.Lock()

    def set_webserver(self, ws: WebServer):
        self._webserver = ws

    def set_tui(self, tui: object):
        self._tui = tui


    def load_playlists(self):
        self.playlists = discover(self.cfg)
        log.info(f"Discovered {len(self.playlists)} playlist(s): {list(self.playlists.keys())}")

    def start(self):
        self._start_outputs()
        self.state = State.STOPPED

        default = self.cfg.playout.default_playlist
        if default and default in self.playlists:
            self._activate(self.playlists[default])
        elif self.playlists:
            self._activate(next(iter(self.playlists.values())))

    def stop(self):
        self._stop_decode.set()
        self._pause_event.set()
        if self._decode_thread:
            self._decode_thread.join(timeout=3)
        self._stop_outputs()
        self.state = State.STOPPED

    def pause(self):
        if self.state == State.PLAYING:
            self._pause_event.clear()
            self.state = State.PAUSED
            if self._webserver:
                self._webserver.broadcast_state_change()

    def resume(self):
        if self.state == State.PAUSED:
            self._pause_event.set()
            self.state = State.PLAYING
            if self._webserver:
                self._webserver.broadcast_state_change()

    def next_track(self):
        with self._lock:
            self._advance()
            self._play_current()

    def prev_track(self):
        with self._lock:
            self._rewind()
            self._play_current()

    def toggle_shuffle(self):
        self._shuffle = not self._shuffle
        self._rebuild_deck()
        log.info(f"Shuffle {'enabled' if self._shuffle else 'disabled'}")
        if self._webserver:
            self._webserver.broadcast_state_change()

    def switch_to(self, name: str, immediate: bool = False):
        if name not in self.playlists:
            return
        pl = self.playlists[name]
        transition = pl.transition or self.cfg.transitions.default

        with self._lock:
            if immediate or transition == "immediate" or self.active_playlist is None:
                self._activate(pl)
            else:
                self._pending_playlist = pl
                log.info(f"Queued switch to '{name}' ({transition})")
                if self._webserver:
                    self._webserver.broadcast_state_change()

    def reload_playlists(self):
        current_name = self.active_playlist.name if self.active_playlist else None
        self.load_playlists()
        if not current_name or current_name not in self.playlists:
            if self.playlists:
                self._activate(next(iter(self.playlists.values())))
        if self._webserver:
            self._webserver.broadcast_state_change()

    @property
    def current_track(self) -> Optional[Track]:
        if not self.active_playlist or not self.active_playlist.tracks:
            return None
        return self.active_playlist.tracks[self._current_index()]

    def _current_index(self) -> int:
        if not self.active_playlist:
            return 0
        if self._shuffle and self._deck:
            return self._deck.current()
        return self._track_index % len(self.active_playlist.tracks)

    def _activate(self, pl: Playlist):
        self.active_playlist = pl
        self._track_index = 0
        self._deck = None
        self._rebuild_deck()
        self._play_current()

    def _rebuild_deck(self):
        if not self.active_playlist:
            return
        n = len(self.active_playlist.tracks)
        if self._shuffle:
            carry = self.cfg.playout.shuffle_carry_over
            if self._deck is None:
                self._deck = ShuffleDeck(n, carry_over=carry)
            else:
                self._deck.reset(n)
        else:
            self._deck = None

    def _advance(self):
        if not self.active_playlist:
            return
        if self._shuffle and self._deck:
            self._deck.advance()
        else:
            n = len(self.active_playlist.tracks)
            self._track_index = (self._track_index + 1) % n

    def _rewind(self):
        if not self.active_playlist:
            return
        if self._shuffle and self._deck:
            self._deck.rewind()
        else:
            n = len(self.active_playlist.tracks)
            self._track_index = (self._track_index - 1) % n

    def _play_current(self):
        if not self.active_playlist or not self.active_playlist.tracks:
            return

        track = self.active_playlist.tracks[self._current_index()]
        self.current_meta = read_metadata(track.path)

        if self.current_meta.title:
            track.title = self.current_meta.title
        if self.current_meta.duration:
            track.duration = self.current_meta.duration

        self.current_meta.save_art()
        self._write_now_playing(track)

        if self._meta_injector:
            self._meta_injector.update(
                title=self.current_meta.title or track.path.stem,
                artist=self.current_meta.artist or "",
                album=self.current_meta.album or "",
            )

        if self._webserver:
            self._webserver.broadcast_track_change()

        if self._tui and hasattr(self._tui, "notify_track_start"):
            self._tui.notify_track_start()

        log.info(f"Playing: {track}")

        self._stop_decode.set()
        if self._decode_thread and self._decode_thread.is_alive():
            self._decode_thread.join(timeout=3)

        self._stop_decode.clear()
        self._track_end_event.clear()
        self.state = State.PLAYING

        self._decode_thread = threading.Thread(
            target=self._decode_loop,
            args=(track.path,),
            daemon=True,
        )
        self._decode_thread.start()

    def _write_now_playing(self, track: Track):
        try:
            meta = self.current_meta
            pl_name = self.active_playlist.name if self.active_playlist else ""
            lines = [
                f"title={meta.title or track.path.stem}",
                f"artist={meta.artist or ''}",
                f"album={meta.album or ''}",
                f"year={meta.year or ''}",
                f"duration={meta.duration or ''}",
                f"playlist={pl_name}",
                f"file={track.path}",
                f"timestamp={datetime.now().isoformat()}",
            ]
            Path("now_playing.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        except Exception as e:
            log.debug(f"now_playing.txt write error: {e}")

    def _decode_loop(self, path: Path):
        bytes_per_sample = self.cfg.playout.channels * 2
        chunk_size = CHUNK_FRAMES * bytes_per_sample

        proc = subprocess.Popen(
            [
                "ffmpeg", "-loglevel", "error",
                "-i", str(path),
                "-f", "s16le",
                "-ar", str(self.cfg.playout.sample_rate),
                "-ac", str(self.cfg.playout.channels),
                "pipe:1",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

        try:
            while not self._stop_decode.is_set():
                self._pause_event.wait()
                if self._stop_decode.is_set():
                    break
                chunk = proc.stdout.read(chunk_size)
                if not chunk:
                    break
                try:
                    self._audio_queue.put(chunk, timeout=1.0)
                except queue.Full:
                    if self._stop_decode.is_set():
                        break
        finally:
            proc.kill()
            proc.wait()

        self._track_end_event.set()

        if not self._stop_decode.is_set():
            self._on_track_end()

    def _on_track_end(self):
        with self._lock:
            if self._pending_playlist is not None:
                pl = self._pending_playlist
                self._pending_playlist = None
                self._activate(pl)
                return
            self._advance()
            self._play_current()

    def _start_outputs(self):
        if self.cfg.soundcard.enabled:
            self._start_soundcard()
        if self.cfg.udp.enabled:
            self._start_udp()

    def _start_soundcard(self):
        try:
            import sounddevice as sd
            import numpy as np

            sr = self.cfg.playout.sample_rate
            ch = self.cfg.playout.channels
            q = self._audio_queue

            def callback(outdata, frames, time_info, status):
                needed = frames * ch * 2
                try:
                    chunk = q.get_nowait()
                except queue.Empty:
                    outdata[:] = np.zeros((frames, ch), dtype=np.float32)
                    return
                if chunk is None:
                    outdata[:] = np.zeros((frames, ch), dtype=np.float32)
                    return
                if len(chunk) < needed:
                    chunk = chunk + b"\x00" * (needed - len(chunk))
                pcm = np.frombuffer(chunk[:needed], dtype=np.int16)
                outdata[:] = pcm.reshape(-1, ch).astype(np.float32) / 32768.0

            self._sd_stream = sd.OutputStream(
                samplerate=sr,
                channels=ch,
                dtype="float32",
                blocksize=CHUNK_FRAMES,
                device=self.cfg.soundcard.device,
                callback=callback,
            )
            self._sd_stream.start()
            log.info("Soundcard output started")

        except ImportError:
            log.warning("sounddevice not installed — soundcard output disabled")
        except Exception as e:
            log.error(f"Soundcard failed to start: {e}")

    def _start_udp(self):
        from .mpegts_meta import MetadataInjector

        cfg = self.cfg.udp
        target = f"udp://{cfg.host}:{cfg.port}"

        self._ffmpeg_udp = subprocess.Popen(
            [
                "ffmpeg", "-loglevel", "error",
                "-f", "s16le",
                "-ar", str(self.cfg.playout.sample_rate),
                "-ac", str(self.cfg.playout.channels),
                "-i", "pipe:0",
                "-c:a", cfg.codec,
                "-b:a", cfg.bitrate,
                "-f", cfg.format,
                "-flush_packets", "1",
                target,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        if cfg.embed_metadata:
            self._meta_injector = MetadataInjector(self._ffmpeg_udp.stdin)

        self._udp_feed_thread = threading.Thread(
            target=self._udp_feed_loop, daemon=True
        )
        self._udp_feed_thread.start()
        log.info(f"UDP output started → {target}")

    def _udp_feed_loop(self):
        while True:
            try:
                chunk = self._audio_queue.get(timeout=0.5)
            except queue.Empty:
                if not (self._ffmpeg_udp and self._ffmpeg_udp.poll() is None):
                    break
                continue
            if chunk is None:
                continue
            try:
                self._ffmpeg_udp.stdin.write(chunk)
                self._ffmpeg_udp.stdin.flush()
            except BrokenPipeError:
                log.error("UDP ffmpeg pipe broken")
                break

    def _stop_outputs(self):
        if self._sd_stream:
            self._sd_stream.stop()
            self._sd_stream.close()
            self._sd_stream = None

        if self._ffmpeg_udp:
            try:
                self._ffmpeg_udp.stdin.close()
            except Exception:
                pass
            self._ffmpeg_udp.kill()
            self._ffmpeg_udp.wait()
            self._ffmpeg_udp = None