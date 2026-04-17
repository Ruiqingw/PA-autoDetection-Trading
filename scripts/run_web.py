"""Run the browser-based dashboard locally."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from aiohttp import web

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import Settings
from webapp.server import create_app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    settings = Settings.from_env()
    app = create_app(settings)
    web.run_app(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
