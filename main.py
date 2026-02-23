import logging
import sys
from pathlib import Path

from haze.config import load
from haze.controller import Controller
from haze.tui import TUI
from haze.webserver import WebServer

logging.basicConfig(
    filename="haze.log",
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)


def main():
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("config.yaml")
    cfg = load(config_path)

    controller = Controller(cfg)
    controller.load_playlists()

    if cfg.web.enabled:
        webserver = WebServer(controller, host=cfg.web.host, port=cfg.web.port)
        controller.set_webserver(webserver)
        webserver.start()

    controller.start()

    try:
        TUI(controller).run()
    except KeyboardInterrupt:
        pass
    finally:
        controller.stop()


if __name__ == "__main__":
    main()