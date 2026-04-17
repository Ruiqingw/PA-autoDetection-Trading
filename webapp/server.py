"""Local aiohttp server for the browser-based trading dashboard."""

from __future__ import annotations

import asyncio
from pathlib import Path
import time

from aiohttp import web

from config.settings import Settings
from services.monitor import build_alert_manager, collect_market_bundles
from storage.sqlite_store import SQLiteStore
from webapp.serializers import build_dashboard_payload


STATIC_DIR = Path(__file__).resolve().parent / "static"
CACHE_TTL_SECONDS = 20.0


async def index(_request: web.Request) -> web.FileResponse:
    return web.FileResponse(STATIC_DIR / "index.html")


async def dashboard_data(request: web.Request) -> web.Response:
    settings: Settings = request.app["settings"]
    store: SQLiteStore = request.app["store"]
    alert_manager = request.app["alert_manager"]
    payload_cache: dict[int, tuple[float, dict[str, object]]] = request.app["payload_cache"]

    symbol = request.query.get("symbol") or settings.monitor.symbols[0]
    try:
        interval = int(request.query.get("interval", settings.monitor.intervals[0]))
    except ValueError:
        interval = settings.monitor.intervals[0]
    if interval not in settings.monitor.intervals:
        interval = settings.monitor.intervals[0]

    cached = payload_cache.get(interval)
    now = time.time()
    if cached is not None and now - cached[0] < CACHE_TTL_SECONDS:
        payload = dict(cached[1])
        payload["selected_symbol"] = symbol if symbol in payload["bundles"] else payload["selected_symbol"]
        return web.json_response(payload)

    bundles = await asyncio.get_running_loop().run_in_executor(
        None,
        lambda: collect_market_bundles(
            settings,
            store,
            alert_manager,
            symbols=settings.monitor.symbols,
            intervals=[interval],
        ),
    )
    payload = build_dashboard_payload(
        bundles,
        settings,
        selected_symbol=symbol,
        selected_interval=interval,
    )
    payload_cache[interval] = (now, payload)
    return web.json_response(payload)


def create_app(settings: Settings | None = None) -> web.Application:
    resolved_settings = settings or Settings.from_env()
    app = web.Application()
    app["settings"] = resolved_settings
    app["store"] = SQLiteStore(resolved_settings.storage.sqlite_path)
    app["alert_manager"] = build_alert_manager(resolved_settings)
    app["payload_cache"] = {}
    app.router.add_get("/", index)
    app.router.add_get("/api/dashboard", dashboard_data)
    app.router.add_static("/static/", STATIC_DIR)
    return app
