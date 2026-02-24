from __future__ import annotations

import os
import sys
import threading
import time
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .controller import Controller

from .controller import State

log = logging.getLogger(__name__)

_USE_CURSES = sys.platform != "win32"


def _fmt_time(secs: float | None) -> str:
    if secs is None:
        return "--:--"
    secs = int(secs)
    return f"{secs // 60}:{secs % 60:02d}"


def _trunc(s: str, n: int) -> str:
    s = s or ""
    return s if len(s) <= n else s[:max(0, n - 1)] + "…"


def _rjust_pair(left: str, right: str, width: int) -> str:
    gap = width - len(left) - len(right)
    return left + " " * max(1, gap) + right


def _progress_bar(elapsed: float, total: float | None, width: int) -> str:
    time_str = f"  {_fmt_time(elapsed)} / {_fmt_time(total)}  "
    inner = width - 2 - len(time_str)
    if inner < 4:
        return f"[{time_str.strip()}]"
    filled = int(inner * min(elapsed, total) / total) if (total and total > 0) else 0
    return "[" + "=" * filled + " " * (inner - filled) + time_str + "]"


def _cols() -> int:
    try:
        return os.get_terminal_size().columns
    except Exception:
        return 80


HELP = "[ 1 ] PLAY  [ 2 ] PAUSE  [ 3 ] STOP  [ 4 ] NEXT  [ 5 ] PREV  [ 6 ] SHUFFLE  [ 7 ] RELOAD  [ Q ] QUIT"
DIV = "─"


def _handle_key(ch: str, controller) -> bool:
    c = controller
    ch = ch.lower()
    if ch in ("q", "\x03", "\x1b"):
        c.stop()
        return False
    elif ch == "1":
        if c.state == State.PAUSED:
            c.resume()
    elif ch == "2":
        c.pause()
    elif ch == "3":
        c.stop()
    elif ch == "4":
        c.next_track()
    elif ch == "5":
        c.prev_track()
    elif ch == "6":
        c.toggle_shuffle()
    elif ch == "7":
        c.reload_playlists()
    return True


class TUI:
    def __init__(self, controller: Controller):
        self.controller = controller
        self._running = False
        self._elapsed: float = 0.0
        self._track_start: float | None = None

    def notify_track_start(self):
        self._track_start = time.monotonic()
        self._elapsed = 0.0

    def run(self):
        self._running = True
        if _USE_CURSES:
            self._run_curses()
        else:
            self._run_windows()

    # ------------------------------------------------------------------ #
    #  Curses backend (Unix)                                               #
    # ------------------------------------------------------------------ #

    def _run_curses(self):
        import curses

        def _main(stdscr):
            curses.curs_set(0)
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_CYAN,    -1)
            curses.init_pair(2, curses.COLOR_GREEN,   -1)
            curses.init_pair(3, curses.COLOR_YELLOW,  -1)
            curses.init_pair(4, curses.COLOR_MAGENTA, -1)
            curses.init_pair(5, curses.COLOR_WHITE,   -1)
            stdscr.nodelay(False)
            stdscr.timeout(500)
            stdscr.keypad(True)

            while self._running:
                self._update_elapsed()
                self._curses_draw(stdscr)

                key = stdscr.getch()
                if key == -1:
                    continue
                try:
                    ch = chr(key)
                except (ValueError, OverflowError):
                    continue
                if not _handle_key(ch, self.controller):
                    self._running = False
                    break

        curses.wrapper(_main)

    def _update_elapsed(self):
        state = self.controller.state
        if self._track_start and state == State.PLAYING:
            self._elapsed = time.monotonic() - self._track_start
        elif state == State.STOPPED:
            self._elapsed = 0.0

    def _curses_draw(self, scr):
        import curses
        scr.erase()
        h, w = scr.getmaxyx()
        c = self.controller
        meta = c.current_meta
        track = c.current_track
        state = c.state

        title  = meta.title  or (track.path.stem if track else "—")
        artist = meta.artist or "—"
        album  = meta.album  or "—"
        year   = f" ({meta.year})" if meta.year else ""
        dur    = meta.duration or (track.duration if track else None)
        codec  = track.path.suffix.lstrip(".").upper() if track else ""

        state_label = {
            State.PLAYING: "▶  PLAYING",
            State.PAUSED:  "⏸  PAUSED",
            State.STOPPED: "⏹  STOPPED",
        }.get(state, "")
        shuffle_str = "  [SHUFFLE ON]" if c._shuffle else ""
        web_str = ""
        if c.cfg.web.enabled:
            host = "localhost" if c.cfg.web.host in ("0.0.0.0", "") else c.cfg.web.host
            web_str = f"  │  http://{host}:{c.cfg.web.port}"

        def put(y, x, text, attr=0):
            if y >= h - 1:
                return
            try:
                scr.addnstr(y, x, str(text), max(0, w - x - 1), attr)
            except curses.error:
                pass

        def div(y):
            if y >= h - 1:
                return
            try:
                scr.addnstr(y, 0, DIV * w, w, curses.color_pair(5))
            except curses.error:
                pass

        row = 0
        div(row); row += 1
        put(row, 0, f"  HAZE PLAYOUT  ·  {state_label}{shuffle_str}{web_str}",
            curses.color_pair(1) | curses.A_BOLD); row += 1
        div(row); row += 1
        put(row, 0, "  " + HELP, curses.color_pair(5)); row += 1
        div(row); row += 1
        row += 1

        put(row, 0, "  NOW PLAYING", curses.color_pair(3) | curses.A_BOLD); row += 1
        row += 1

        title_line = f"  {_trunc(title, w - 12)}"
        put(row, 0, _rjust_pair(title_line, f"{codec}  ", w),
            curses.color_pair(2) | curses.A_BOLD); row += 1
        put(row, 2, _trunc(artist, w - 4), curses.color_pair(5)); row += 1
        put(row, 2, _trunc(album + year, w - 4), curses.color_pair(4)); row += 1
        row += 1
        put(row, 0, "  " + _progress_bar(self._elapsed, dur, w - 4),
            curses.color_pair(1)); row += 1
        row += 1
        div(row); row += 1
        row += 1

        pl = c.active_playlist
        if pl and row < h - 4:
            idx = c._current_index()
            n = len(pl.tracks)
            upcoming = [pl.tracks[(idx + i) % n] for i in range(1, min(6, n))]
            if upcoming:
                put(row, 0, f"  NEXT UP  ·  Playlist: \"{pl.name}\"",
                    curses.color_pair(3)); row += 1
                row += 1
                col_w = max(10, (w - 6) // 4)
                hdr = f"  {'Title':<{col_w}}{'Artist':<{col_w}}{'Album':<{col_w}}{'Length':>8}"
                put(row, 0, _trunc(hdr, w),
                    curses.color_pair(5) | curses.A_UNDERLINE); row += 1
                for t in upcoming:
                    if row >= h - 1:
                        break
                    row_str = (
                        f"  {_trunc(t.title or t.path.stem, col_w - 1):<{col_w}}"
                        f"{'—':<{col_w}}{'—':<{col_w}}{_fmt_time(t.duration):>8}"
                    )
                    put(row, 0, _trunc(row_str, w), curses.color_pair(5)); row += 1

        scr.refresh()

    # ------------------------------------------------------------------ #
    #  Windows plain-terminal backend                                      #
    # ------------------------------------------------------------------ #

    def _run_windows(self):
        import msvcrt

        threading.Thread(target=self._windows_refresh_loop, daemon=True).start()

        while self._running:
            if msvcrt.kbhit():
                ch = msvcrt.getwch()
                if not _handle_key(ch, self.controller):
                    self._running = False
                    break
            time.sleep(0.05)

    def _windows_refresh_loop(self):
        while self._running:
            try:
                self._update_elapsed()
                self._windows_draw()
            except Exception as e:
                log.debug(f"TUI render error: {e}")
            time.sleep(0.5)

    def _windows_draw(self):
        c = self.controller
        w = _cols()
        meta = c.current_meta
        track = c.current_track
        state = c.state

        title  = meta.title  or (track.path.stem if track else "—")
        artist = meta.artist or "—"
        album  = meta.album  or "—"
        year   = f" ({meta.year})" if meta.year else ""
        dur    = meta.duration or (track.duration if track else None)
        codec  = track.path.suffix.lstrip(".").upper() if track else ""

        state_label = {
            State.PLAYING: "▶  PLAYING",
            State.PAUSED:  "⏸  PAUSED",
            State.STOPPED: "⏹  STOPPED",
        }.get(state, "")
        shuffle_str = "  [SHUFFLE ON]" if c._shuffle else ""
        web_str = ""
        if c.cfg.web.enabled:
            host = "localhost" if c.cfg.web.host in ("0.0.0.0", "") else c.cfg.web.host
            web_str = f"  │  http://{host}:{c.cfg.web.port}"

        div = DIV * w
        lines = [
            "",
            div,
            f"  HAZE PLAYOUT  ·  {state_label}{shuffle_str}{web_str}",
            div,
            "  " + HELP,
            div,
            "",
            "  NOW PLAYING",
            "",
            _rjust_pair(f"  {_trunc(title, w - 12)}", f"{codec}  ", w),
            f"  {_trunc(artist, w - 4)}",
            f"  {_trunc(album + year, w - 4)}",
            "",
            "  " + _progress_bar(self._elapsed, dur, w - 4),
            "",
            div,
            "",
        ]

        pl = c.active_playlist
        if pl:
            idx = c._current_index()
            n = len(pl.tracks)
            upcoming = [pl.tracks[(idx + i) % n] for i in range(1, min(6, n))]
            if upcoming:
                col_w = max(10, (w - 6) // 4)
                lines.append(f"  NEXT UP  ·  Playlist: \"{pl.name}\"")
                lines.append("")
                lines.append(_trunc(
                    f"  {'Title':<{col_w}}{'Artist':<{col_w}}{'Album':<{col_w}}{'Length':>8}", w))
                lines.append("  " + DIV * (w - 2))
                for t in upcoming:
                    lines.append(_trunc(
                        f"  {_trunc(t.title or t.path.stem, col_w-1):<{col_w}}"
                        f"{'—':<{col_w}}{'—':<{col_w}}{_fmt_time(t.duration):>8}", w))
                lines.append("")
                lines.append(div)

        os.system("cls")
        print("\n".join(lines), flush=True)