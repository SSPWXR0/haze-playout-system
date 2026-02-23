from __future__ import annotations

import curses
import threading
import time
import logging
from typing import TYPE_CHECKING

from .controller import State

if TYPE_CHECKING:
    from .controller import Controller

log = logging.getLogger(__name__)

KEYBINDINGS = [
    ("SPACE",  "Play / Pause"),
    ("→ / n",  "Next track"),
    ("← / p",  "Prev track"),
    ("↑ / ↓",  "Select playlist"),
    ("ENTER",  "Switch to selected"),
    ("s",      "Toggle shuffle"),
    ("r",      "Reload playlists"),
    ("q",      "Quit"),
]


class TUI:
    def __init__(self, controller: Controller):
        self.controller = controller
        self._selected: int = 0
        self._running = False

    def run(self):
        curses.wrapper(self._main)

    def _main(self, stdscr: curses.window):
        self._running = True
        curses.curs_set(0)
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN,    -1)
        curses.init_pair(2, curses.COLOR_GREEN,   -1)
        curses.init_pair(3, curses.COLOR_YELLOW,  -1)
        curses.init_pair(4, curses.COLOR_MAGENTA, -1)
        curses.init_pair(5, curses.COLOR_WHITE,   -1)
        curses.init_pair(6, curses.COLOR_BLACK,   curses.COLOR_CYAN)

        stdscr.nodelay(True)
        stdscr.keypad(True)

        threading.Thread(target=self._refresh_loop, args=(stdscr,), daemon=True).start()

        while self._running:
            try:
                key = stdscr.getch()
            except Exception:
                key = -1
            if key == -1:
                time.sleep(0.05)
                continue
            self._handle_key(key)

    def _handle_key(self, key: int):
        c = self.controller
        names = list(c.playlists.keys())

        if key in (ord("q"), ord("Q")):
            self._running = False
            c.stop()
        elif key == ord(" "):
            if c.state == State.PAUSED:
                c.resume()
            else:
                c.pause()
        elif key in (curses.KEY_RIGHT, ord("n"), ord("N")):
            c.next_track()
        elif key in (curses.KEY_LEFT, ord("p"), ord("P")):
            c.prev_track()
        elif key == curses.KEY_UP:
            self._selected = max(0, self._selected - 1)
        elif key == curses.KEY_DOWN:
            self._selected = min(len(names) - 1, self._selected + 1)
        elif key in (curses.KEY_ENTER, 10, 13):
            if names:
                c.switch_to(names[self._selected])
        elif key in (ord("s"), ord("S")):
            c.toggle_shuffle()
        elif key in (ord("r"), ord("R")):
            c.reload_playlists()
            self._selected = 0

    def _refresh_loop(self, stdscr: curses.window):
        while self._running:
            try:
                self._draw(stdscr)
            except Exception:
                pass
            time.sleep(0.25)

    def _draw(self, scr: curses.window):
        scr.erase()
        h, w = scr.getmaxyx()
        self._draw_header(scr, w)
        self._draw_now_playing(scr, w, y=2)
        self._draw_playlists(scr, w, y_start=9, max_rows=h - len(KEYBINDINGS) - 11)
        self._draw_keybindings(scr, w, h)
        scr.refresh()

    def _draw_header(self, scr: curses.window, w: int):
        scr.attron(curses.color_pair(1) | curses.A_BOLD)
        scr.addstr(0, 0, " ▶  HAZE PLAYOUT ".center(w)[:w])
        scr.attroff(curses.color_pair(1) | curses.A_BOLD)

    def _draw_now_playing(self, scr: curses.window, w: int, y: int):
        c = self.controller
        meta = c.current_meta
        track = c.current_track

        state_label = {
            State.PLAYING: "▶ PLAYING",
            State.PAUSED:  "⏸ PAUSED",
            State.STOPPED: "⏹ STOPPED",
        }.get(c.state, "")

        pl_name = c.active_playlist.name if c.active_playlist else "—"
        shuffle_tag = "  [SHUFFLE]" if c._shuffle else ""
        pending_tag = f"  ↷ {c._pending_playlist.name}" if c._pending_playlist else ""

        scr.attron(curses.color_pair(3))
        scr.addstr(y, 2, f"{state_label}  │  {pl_name}{shuffle_tag}{pending_tag}"[:w - 3])
        scr.attroff(curses.color_pair(3))

        title = meta.title or (track.path.stem if track else "—")
        scr.attron(curses.color_pair(2) | curses.A_BOLD)
        scr.addstr(y + 1, 2, f"♪  {title}"[:w - 3])
        scr.attroff(curses.color_pair(2) | curses.A_BOLD)

        if meta.artist:
            scr.attron(curses.color_pair(5))
            scr.addstr(y + 2, 4, f"{meta.artist}"[:w - 5])
            scr.attroff(curses.color_pair(5))

        if meta.album:
            year_str = f" ({meta.year})" if meta.year else ""
            scr.attron(curses.color_pair(4))
            scr.addstr(y + 3, 4, f"{meta.album}{year_str}"[:w - 5])
            scr.attroff(curses.color_pair(4))

        dur = meta.duration or (track.duration if track else None)
        if dur:
            mins, secs = divmod(int(dur), 60)
            scr.attron(curses.color_pair(1))
            scr.addstr(y + 4, 4, f"{mins}:{secs:02d}"[:w - 5])
            scr.attroff(curses.color_pair(1))

        cfg = c.cfg.web
        if cfg.enabled:
            host_display = "localhost" if cfg.host in ("0.0.0.0", "") else cfg.host
            scr.attron(curses.color_pair(3))
            scr.addstr(y + 5, 4, f"Web UI → http://{host_display}:{cfg.port}"[:w - 5])
            scr.attroff(curses.color_pair(3))

    def _draw_playlists(self, scr: curses.window, w: int, y_start: int, max_rows: int):
        c = self.controller
        names = list(c.playlists.keys())
        active_name = c.active_playlist.name if c.active_playlist else None

        scr.attron(curses.color_pair(5) | curses.A_UNDERLINE)
        scr.addstr(y_start, 2, "Playlists"[:w - 3])
        scr.attroff(curses.color_pair(5) | curses.A_UNDERLINE)

        if not names:
            scr.addstr(y_start + 1, 4, "No playlists found — add files to Managed/Playlists/"[:w - 5])
            return

        visible_start = max(0, self._selected - max_rows + 2)
        for i, name in enumerate(names[visible_start:visible_start + max_rows]):
            actual = i + visible_start
            row = y_start + 1 + i
            pl = c.playlists[name]
            is_active = name == active_name
            is_selected = actual == self._selected

            prefix = "▶ " if is_active else "  "
            label = f"{prefix}{name}  ({len(pl)} tracks, {pl.transition})"

            if is_active and is_selected:
                attr = curses.color_pair(6) | curses.A_BOLD
            elif is_active:
                attr = curses.color_pair(2) | curses.A_BOLD
            elif is_selected:
                attr = curses.color_pair(6)
            else:
                attr = curses.color_pair(5)

            scr.attron(attr)
            scr.addstr(row, 2, label[:w - 3])
            scr.attroff(attr)

    def _draw_keybindings(self, scr: curses.window, w: int, h: int):
        y = h - len(KEYBINDINGS) - 1
        scr.attron(curses.color_pair(5) | curses.A_UNDERLINE)
        scr.addstr(y, 2, "Keys"[:w - 3])
        scr.attroff(curses.color_pair(5) | curses.A_UNDERLINE)
        for i, (key, desc) in enumerate(KEYBINDINGS):
            scr.attron(curses.color_pair(1))
            scr.addstr(y + 1 + i, 4, f"{key:<10}"[:10])
            scr.attroff(curses.color_pair(1))
            scr.addstr(y + 1 + i, 14, desc[:w - 15])