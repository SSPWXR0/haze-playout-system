from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .controller import Controller

log = logging.getLogger(__name__)

_WEB_DIR = Path(__file__).parent / "web"


class WebServer:
    def __init__(self, controller: Controller, host: str = "0.0.0.0", port: int = 8080):
        self.controller = controller
        self.host = host
        self.port = port
        self._thread: Optional[threading.Thread] = None
        self._socketio = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        log.info(f"Web UI starting on http://{self.host}:{self.port}")

    def _run(self):
        try:
            from flask import Flask, abort, Response
            from flask_socketio import SocketIO, emit
        except ImportError:
            log.error("Flask or flask-socketio not installed — run: pip install flask flask-socketio")
            return

        app = Flask(__name__, static_folder=None)
        app.config["SECRET_KEY"] = "haze-playout"
        socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")
        self._socketio = socketio

        @app.route("/")
        @app.route("/index.html")
        def index():
            path = _WEB_DIR / "index.html"
            if not path.exists():
                return f"index.html not found at {path}", 404
            return Response(path.read_bytes(), mimetype="text/html; charset=utf-8")

        @app.route("/art")
        def art():
            art_path = Path("now_playing_art.jpg")
            
            attempts = 0
            while not art_path.exists() and attempts < 5:
                time.sleep(0.1)
                attempts += 1

            if not art_path.exists():
                abort(404)
            
            try:
                data = art_path.read_bytes()
                return Response(data, mimetype="image/jpeg", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
            except Exception:
                abort(503)

        @socketio.on("connect")
        def on_connect():
            log.info("WebSocket client connected")
            emit("state", self._build_state())

        @socketio.on("action")
        def on_action(data):
            if not isinstance(data, dict):
                return
            action = data.get("action")
            c = self.controller

            if action == "play":
                c.resume()
            elif action == "pause":
                c.pause()
            elif action == "next":
                c.next_track()
            elif action == "prev":
                c.prev_track()
            elif action == "toggle_shuffle":
                c.toggle_shuffle()
            elif action == "switch":
                name = data.get("playlist")
                if name:
                    c.switch_to(name)

            socketio.emit("state", self._build_state())

        socketio.run(app, host=self.host, port=self.port, use_reloader=False, log_output=False)

    def broadcast_track_change(self):
        self._emit("track_change", self._build_state())

    def broadcast_state_change(self):
        self._emit("state", self._build_state())

    def _emit(self, event: str, data: dict):
        if self._socketio is None:
            return
        try:
            self._socketio.emit(event, data)
        except Exception as e:
            log.debug(f"SocketIO emit error: {e}")

    def _build_state(self) -> dict:
        c = self.controller
        meta = c.current_meta
        track = c.current_track

        playlists = [
            {
                "name": name,
                "track_count": len(pl),
                "transition": pl.transition or "finish_track",
                "active": bool(c.active_playlist and c.active_playlist.name == name),
            }
            for name, pl in c.playlists.items()
        ]

        return {
            "state": c.state.name,
            "shuffle": c._shuffle,
            "playlist": c.active_playlist.name if c.active_playlist else None,
            "pending_playlist": c._pending_playlist.name if c._pending_playlist else None,
            "playlists": playlists,
            "track": {
                "title": meta.title or (track.path.stem if track else None),
                "artist": meta.artist,
                "album": meta.album,
                "year": meta.year,
                "duration": meta.duration,
                "has_art": meta.has_art,
            },
        }