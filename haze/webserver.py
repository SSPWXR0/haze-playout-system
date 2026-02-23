from __future__ import annotations

import asyncio
import json
import logging
import threading
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .controller import Controller

log = logging.getLogger(__name__)

_WEB_DIR = Path(__file__).parent / "web"
if not _WEB_DIR.exists():
    alt = Path(__file__).parent.parent / "web"
    if alt.exists():
        log.debug("webserver: primary web dir not found, using %s", alt)
        _WEB_DIR = alt
    else:
        log.debug("webserver: no web directory found at %s or %s", _WEB_DIR, alt)


class WebServer:
    def __init__(self, controller: Controller, host: str = "0.0.0.0", port: int = 8080):
        self.controller = controller
        self.host = host
        self.port = port
        self._clients: set = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        log.info(f"Web UI starting on http://{self.host}:{self.port}")

    def _run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._serve())

    async def _serve(self):
        try:
            import websockets.server as ws_server
        except ImportError:
            log.error("websockets not installed — run: pip install websockets")
            return

        async def ws_handler(websocket):
            self._clients.add(websocket)
            log.info(f"WS client connected: {websocket.remote_address}")
            try:
                await websocket.send(json.dumps(self._build_state()))
                async for msg in websocket:
                    await self._handle_ws_message(msg)
            except Exception:
                pass
            finally:
                self._clients.discard(websocket)

        async def http_handler(reader, writer):
            try:
                request_line = await reader.readline()
                while True:
                    line = await reader.readline()
                    if line in (b"\r\n", b"\n", b""):
                        break

                parts = request_line.decode(errors="replace").split(" ")
                path = parts[1].split("?")[0] if len(parts) > 1 else "/"

                if path in ("/", "/index.html"):
                    html_path = _WEB_DIR / "index.html"
                    content = html_path.read_bytes() if html_path.exists() else b"<h1>index.html missing</h1>"
                    ct = "text/html; charset=utf-8"
                elif path == "/art":
                    art_path = Path("now_playing_art.jpg")
                    if art_path.exists():
                        content = art_path.read_bytes()
                        ct = "image/jpeg"
                    else:
                        writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n")
                        await writer.drain()
                        writer.close()
                        return
                else:
                    writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n")
                    await writer.drain()
                    writer.close()
                    return

                response = (
                    f"HTTP/1.1 200 OK\r\n"
                    f"Content-Type: {ct}\r\n"
                    f"Content-Length: {len(content)}\r\n"
                    f"Cache-Control: no-cache\r\n"
                    f"Connection: close\r\n\r\n"
                ).encode() + content
                writer.write(response)
                await writer.drain()
                writer.close()
            except Exception as e:
                log.debug(f"HTTP error: {e}")
                try:
                    writer.close()
                except Exception:
                    pass

        http_srv = await asyncio.start_server(http_handler, self.host, self.port)
        ws_srv = await ws_server.serve(ws_handler, self.host, self.port + 1)

        async with http_srv, ws_srv:
            await asyncio.Future()

    async def _handle_ws_message(self, raw: str):
        try:
            msg = json.loads(raw)
        except Exception:
            return

        action = msg.get("action")
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
            name = msg.get("playlist")
            if name:
                c.switch_to(name)

        self.broadcast_state_change()

    def broadcast(self, event: dict):
        if not self._clients or self._loop is None:
            return
        msg = json.dumps(event)
        asyncio.run_coroutine_threadsafe(self._broadcast_async(msg), self._loop)

    async def _broadcast_async(self, msg: str):
        dead = set()
        for client in list(self._clients):
            try:
                await client.send(msg)
            except Exception:
                dead.add(client)
        self._clients -= dead

    def broadcast_track_change(self):
        self.broadcast({"type": "track_change", **self._build_state()})

    def broadcast_state_change(self):
        self.broadcast({"type": "state_change", **self._build_state()})

    def _build_state(self) -> dict[str, object]:
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
            "shuffle": c.shuffle,
            "playlist": c.active_playlist.name if c.active_playlist else None,
            "pending_playlist": c.pending_playlist.name if c.pending_playlist else None,
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