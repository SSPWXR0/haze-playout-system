import logging
import os
import sys
import argparse
from pathlib import Path
import time

from haze.config import load
from haze.controller import Controller
from haze.tui import TUI
from haze.webserver import WebServer

logging.basicConfig(
    filename="haze.log",
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)


def main(
    config_path: Path,
    list_devices: bool = False,
    list_playlists: bool = False,
    no_tui: bool = False,
):

    cfg = load(config_path)

    if not os.path.exists("Managed") and not os.path.exists("Playlists"):
        logging.warning(
            "Neither 'Managed' nor 'Playlists' directories exist. Creating 'Managed'."
        )
        os.makedirs("Managed", exist_ok=True)

    if list_devices:
        try:
            import sounddevice as sd
        except ImportError:
            print("sounddevice not installed; cannot list devices.")
            sys.exit(1)
        devices = sd.query_devices()
        for idx, dev in enumerate(devices):
            print(
                f"{idx:2d}: {dev['name']} (max_out={dev.get('max_output_channels')})"
            )
        return

    controller = Controller(cfg)
    controller.load_playlists()

    if list_playlists:
        for name in controller.playlists.keys():
            print(name)
        return

    tui: TUI | None = None
    if not no_tui:
        tui = TUI(controller)
        controller.set_tui(tui)

    if cfg.web.enabled:
        webserver = WebServer(controller, host=cfg.web.host, port=cfg.web.port)
        controller.set_webserver(webserver)
        webserver.start()

    controller.start()

    try:
        if tui:
            tui.run()
        else:
            
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        controller.stop()


if __name__ == "__main__":
    args = argparse.ArgumentParser(description="Haze Playout System")
    args.add_argument("--config", "-c", type=Path, default=Path("config.yaml"), help="Path to configuration file")
    args.add_argument("--list-devices", action="store_true", help="List available audio output devices and exit")
    args.add_argument("--list-playlists", action="store_true", help="List available playlists and exit")
    args.add_argument("--no-tui", action="store_true", help="Run without TUI (Terminal User Interface). Only logging will be available.")
    parsed = args.parse_args()

    main(
        config_path=parsed.config,
        list_devices=parsed.list_devices,
        list_playlists=parsed.list_playlists,
        no_tui=parsed.no_tui,
    )