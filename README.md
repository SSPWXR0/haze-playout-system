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

### Command‑line options

```
--config, -c PATH     Use an alternate configuration file (defaults to `config.yaml`)
--list-devices        Print available audio output devices and exit
--list-playlists      Show discovered playlist names and exit
--no-tui              Run headless without the terminal user interface (control via logs or web UI)
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
  soundcard:
    enabled: true
    device: null                  # null = system default

transitions:
  default: finish_track           # finish_track | immediate | crossfade
  crossfade_duration: 2.0

paths:
  playlists_dir: "Managed/Playlists"
```

## Architecture

```
main.py
  └─ PlayoutController      orchestrates playlists + transitions
       ├─ AudioEngine        decodes via ffmpeg, fans out to outputs
       │    └─ sounddevice   local audio output
       └─ TUI (curses)       operator interface
```


## Logs

Runtime logs are written to `haze.log` in the working directory.