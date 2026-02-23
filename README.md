# Haze Playout System

A lightweight, Python-powered music playlist and playout system with a terminal UI.

## Requirements

- Python 3.11+
- `ffmpeg` on PATH
- Python packages: `pip install -r requirements.txt`

## Setup

```
pip install -r requirements.txt
python main.py
```

Or point at a custom config:

```
python main.py /path/to/config.yaml
```

## Playlist Discovery

Drop content into `Managed/Playlists/`:

| Type | How |
|---|---|
| Folder | Subdirectory containing audio files — discovered alphabetically |
| M3U / M3U8 | UTF-8 encoded, relative paths to audio files |
| XSPF | UTF-8 encoded XML, `<location>` as relative paths or `file://` URIs |

Any format supported by ffmpeg is valid as an audio file.

## Configuration (`config.yaml`)

```yaml
playout:
  sample_rate: 48000
  channels: 2
  default_playlist: my_playlist   # null = first discovered
  shuffle: false

outputs:
  udp:
    enabled: false
    host: "127.0.0.1"
    port: 1234
    bitrate: "192k"
    codec: aac
    format: mpegts
  soundcard:
    enabled: true
    device: null                  # null = system default

transitions:
  default: finish_track           # finish_track | immediate | crossfade
  crossfade_duration: 2.0

paths:
  playlists_dir: "Managed/Playlists"
```

### Per-Playlist Transition Override

Playlist-level transition config is not yet in a UI — set it programmatically by editing the `Playlist` objects after discovery, or add a sidecar `.yaml` per playlist (future feature).

## TUI Keybindings

| Key | Action |
|---|---|
| `SPACE` | Play / Pause |
| `→` or `n` | Next track |
| `←` or `p` | Previous track |
| `↑ / ↓` | Navigate playlist list |
| `ENTER` | Switch to selected playlist |
| `s` | Toggle shuffle |
| `r` | Reload playlists from disk |
| `q` | Quit |

## Architecture

```
main.py
  └─ PlayoutController      orchestrates playlists + transitions
       ├─ AudioEngine        decodes via ffmpeg, fans out to outputs
       │    ├─ sounddevice   local audio output
       │    └─ ffmpeg UDP    AAC/MPEG-TS over UDP
       └─ TUI (curses)       operator interface
```

## Receiving the UDP Stream

```bash
ffplay -f mpegts udp://127.0.0.1:1234
```

## Logs

Runtime logs are written to `haze.log` in the working directory.