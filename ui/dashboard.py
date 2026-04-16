"""TradingView-inspired desktop dashboard for the trading assistant."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path.cwd() / ".mplconfig"))

import queue
import threading
import tkinter as tk
from dataclasses import dataclass
from datetime import UTC

from config.settings import Settings, format_timeframe_label
from services.monitor import MonitorBundle, build_alert_manager, collect_market_bundles
from storage.sqlite_store import SQLiteStore
from ui.canvas_chart import TradingChartCanvas
from ui.charts import EMA_12_COLOR, EMA_144_COLOR, EMA_169_COLOR, EMA_238_COLOR, EMA_338_COLOR, summarize_market_chart


APP_BG = "#0e130f"
CHROME_BG = "#131814"
PANEL_BG = "#101511"
PANEL_SOFT_BG = "#171e18"
BORDER = "#29332b"
TEXT = "#f3f5f7"
TEXT_SOFT = "#b6bcc5"
TEXT_DIM = "#7f8792"
GREEN = "#22ab94"
RED = "#f23645"
BLUE = EMA_144_COLOR
ORANGE = EMA_12_COLOR
CHART_HEADER_BG = "#d7ead3"
CHART_TEXT = "#101316"
INDICATOR_OPTIONS: tuple[tuple[str, str], ...] = (
    ("delta", "Delta"),
    ("bid_ask", "Bid / Ask"),
)


def _format_price(value: float) -> str:
    return f"{value:,.2f}"


def _format_change(value: float, percent: float) -> tuple[str, str]:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:,.2f}", f"{sign}{percent:.2f}%"


def _format_compact_number(value: float) -> str:
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if abs(value) >= 1_000:
        return f"{value / 1_000:.2f}K"
    if abs(value) >= 1:
        return f"{value:,.2f}"
    return f"{value:.4f}"


def _format_timeframe_tooltip(interval_minutes: int) -> str:
    if interval_minutes < 60:
        return f"{interval_minutes}分钟"
    if interval_minutes % 1440 == 0:
        days = interval_minutes // 1440
        return f"{days}天"
    if interval_minutes % 60 == 0:
        hours = interval_minutes // 60
        return f"{hours}小时"
    return f"{interval_minutes}分钟"


def _display_symbol(symbol: str) -> str:
    return symbol.replace("/", "")


def _display_market_name(symbol: str) -> str:
    names = {
        "BTC/USD": "Bitcoin / US Dollar",
        "ETH/USD": "Ethereum / US Dollar",
        "SOL/USD": "Solana / US Dollar",
    }
    return names.get(symbol, symbol.replace("/", " / "))


def _symbol_badge(symbol: str) -> tuple[str, str, str]:
    if symbol.startswith("BTC"):
        return "B", "#f7931a", "#ffffff"
    if symbol.startswith("ETH"):
        return "E", "#627eea", "#ffffff"
    if symbol.startswith("SOL"):
        return "S", "#14f195", "#0f1113"
    return symbol[0], BLUE, "#ffffff"


@dataclass(slots=True)
class WatchRowWidgets:
    frame: tk.Frame
    symbol_primary: tk.Label
    symbol_secondary: tk.Label
    last_value: tk.Label
    change_value: tk.Label
    percent_value: tk.Label
    widgets: list[tk.Widget]


class TradingAssistantApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Crypto Trading Assistant")
        self.root.geometry("1560x980")
        self.root.minsize(1280, 860)
        self.root.configure(bg=APP_BG)

        self.settings = Settings.from_env()
        self.store = SQLiteStore(self.settings.storage.sqlite_path)
        self.alert_manager = build_alert_manager(self.settings)
        default_interval = 60 if 60 in self.settings.monitor.intervals else self.settings.monitor.intervals[0]

        self.selected_symbol = self.settings.monitor.symbols[0]
        self.selected_interval = default_interval
        self.auto_refresh_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Waiting for first refresh…")
        self.symbol_chip_var = tk.StringVar(value=_display_symbol(self.selected_symbol))
        self.chart_title_var = tk.StringVar(value="Loading market data…")
        self.chart_context_var = tk.StringVar(value="")
        self.open_var = tk.StringVar(value="O --")
        self.high_var = tk.StringVar(value="H --")
        self.low_var = tk.StringVar(value="L --")
        self.close_var = tk.StringVar(value="C --")
        self.change_var = tk.StringVar(value="--")
        self.ema_12_var = tk.StringVar(value="EMA 12 --")
        self.ema_144_var = tk.StringVar(value="EMA 144 --")
        self.ema_169_var = tk.StringVar(value="EMA 169 --")
        self.ema_238_var = tk.StringVar(value="EMA 238 --")
        self.ema_338_var = tk.StringVar(value="EMA 338 --")
        self.setup_note_var = tk.StringVar(value="Refreshing market data from Kraken…")
        self.bottom_meta_var = tk.StringVar(value="Waiting for first refresh…")

        self.setup_value_labels: dict[str, tk.Label] = {}
        self.timeframe_buttons: dict[int, tk.Label] = {}
        self.chart_mode_buttons: dict[str, tk.Label] = {}
        self.indicator_row_widgets: dict[str, list[tk.Widget]] = {}
        self.watch_rows: dict[str, WatchRowWidgets] = {}
        self.chart_widget: TradingChartCanvas | None = None
        self.chart_mount: tk.Frame | None = None
        self.current_bundle: MonitorBundle | None = None
        self.current_bundles: dict[str, MonitorBundle] = {}
        self._queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._loading = False
        self._auto_refresh_job: str | None = None
        self._hovered_timeframe: int | None = None
        self._timeframe_tooltip: tk.Toplevel | None = None
        self._indicators_popup: tk.Toplevel | None = None
        self.chart_mode = "candles"
        self.selected_indicators = ["delta", "bid_ask"]
        self.auto_button: tk.Button | None = None
        self.refresh_button: tk.Button | None = None
        self.status_chip: tk.Label | None = None
        self.indicators_button: tk.Label | None = None

        self._build_layout()
        self.root.bind_all("<Button-1>", self._handle_global_click, add="+")
        self.root.after(250, self._drain_queue)
        self.root.after(400, self.refresh_data)

    def _build_layout(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        page = tk.Frame(self.root, bg=APP_BG)
        page.grid(row=0, column=0, sticky="nsew", padx=18, pady=18)
        page.columnconfigure(0, weight=1)
        page.rowconfigure(1, weight=1)

        page_head = tk.Frame(page, bg=PANEL_SOFT_BG, highlightbackground=BORDER, highlightthickness=1)
        page_head.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        page_head.grid_columnconfigure(0, weight=1)

        head_text = tk.Frame(page_head, bg=PANEL_SOFT_BG)
        head_text.grid(row=0, column=0, sticky="w", padx=14, pady=12)
        tk.Label(
            head_text,
            text="Version A Baseline",
            bg=PANEL_SOFT_BG,
            fg=TEXT,
            font=("Helvetica", 16, "bold"),
        ).pack(anchor="w")
        tk.Label(
            head_text,
            text="TradingView-inspired shell with live Kraken market snapshots and assistant setup context.",
            bg=PANEL_SOFT_BG,
            fg=TEXT_SOFT,
            font=("Helvetica", 12),
        ).pack(anchor="w", pady=(4, 0))
        tk.Label(
            page_head,
            text="TradingView-inspired shell",
            bg="#1d2c47",
            fg="#d9e4ff",
            padx=12,
            pady=8,
            font=("Helvetica", 11),
        ).grid(row=0, column=1, sticky="e", padx=14, pady=12)

        app = tk.Frame(page, bg=CHROME_BG, highlightbackground=BORDER, highlightthickness=1)
        app.grid(row=1, column=0, sticky="nsew")
        app.columnconfigure(1, weight=1)
        app.rowconfigure(1, weight=1)

        toolbar = tk.Frame(app, bg=PANEL_BG, highlightbackground=BORDER, highlightthickness=1)
        toolbar.grid(row=0, column=0, rowspan=3, sticky="ns", padx=(14, 12), pady=14)
        self._build_toolbar(toolbar)

        topbar = tk.Frame(app, bg=PANEL_BG, highlightbackground=BORDER, highlightthickness=1)
        topbar.grid(row=0, column=1, columnspan=2, sticky="ew", padx=(0, 14), pady=(14, 12))
        topbar.columnconfigure(0, weight=1)
        topbar.columnconfigure(1, weight=0)
        self._build_topbar(topbar)

        main = tk.Frame(app, bg=CHROME_BG)
        main.grid(row=1, column=1, sticky="nsew", padx=(0, 12))
        main.columnconfigure(0, weight=1)
        main.rowconfigure(1, weight=1)
        self._build_main_panel(main)

        sidebar = tk.Frame(app, bg=CHROME_BG)
        sidebar.grid(row=1, column=2, sticky="ns", padx=(0, 14))
        self._build_sidebar(sidebar)

        bottom = tk.Frame(app, bg=PANEL_BG, highlightbackground=BORDER, highlightthickness=1)
        bottom.grid(row=2, column=1, columnspan=2, sticky="ew", padx=(0, 14), pady=(0, 14))
        self._build_bottom_bar(bottom)

    def _build_toolbar(self, parent: tk.Frame) -> None:
        tool_groups = [
            ["≡", "↗", "⌁", "⊕"],
            ["╱", "▦", "☰"],
            ["◔"],
        ]
        for group_index, group in enumerate(tool_groups):
            frame = tk.Frame(parent, bg=PANEL_BG)
            frame.grid(row=group_index, column=0, padx=6, pady=(10 if group_index == 0 else 4, 6), sticky="n")
            for item_index, symbol in enumerate(group):
                label = tk.Label(
                    frame,
                    text=symbol,
                    width=3,
                    height=1,
                    bg=PANEL_BG if not (group_index == 0 and item_index == 0) else "#1f2822",
                    fg=TEXT if group_index == 0 and item_index == 0 else "#cfd4db",
                    font=("Helvetica", 18),
                    padx=8,
                    pady=10,
                    highlightbackground="#2f3d31" if group_index == 0 and item_index == 0 else PANEL_BG,
                    highlightthickness=1 if group_index == 0 and item_index == 0 else 0,
                )
                label.pack(pady=4)

    def _build_topbar(self, parent: tk.Frame) -> None:
        left = tk.Frame(parent, bg=PANEL_BG)
        left.grid(row=0, column=0, sticky="w", padx=12, pady=8)
        right = tk.Frame(parent, bg=PANEL_BG)
        right.grid(row=0, column=1, sticky="e", padx=12, pady=8)

        self.symbol_chip = self._make_chip(left, textvariable=self.symbol_chip_var, badge_symbol="B", badge_bg="#f7931a", active=True)
        self.symbol_chip.pack(side="left", padx=(0, 8))

        for interval in self.settings.monitor.intervals:
            button = self._make_timeframe_button(
                left,
                text=format_timeframe_label(interval),
            )
            button.pack(side="left", padx=(0, 8))
            button.bind("<Button-1>", lambda _event, value=interval: self._set_interval(value))
            button.bind("<Enter>", lambda _event, value=interval, widget=button: self._on_timeframe_hover_enter(value, widget))
            button.bind("<Leave>", lambda _event, value=interval: self._on_timeframe_hover_leave(value))
            self.timeframe_buttons[interval] = button

        for mode, label in (("candles", "Candles"), ("footprint", "Footprint")):
            button = self._make_timeframe_button(left, text=label)
            button.pack(side="left", padx=(0, 8))
            button.bind("<Button-1>", lambda _event, value=mode: self._set_chart_mode(value))
            self.chart_mode_buttons[mode] = button

        self.indicators_button = self._make_timeframe_button(left, text="Indicators")
        self.indicators_button.pack(side="left", padx=(0, 8))
        self.indicators_button.bind("<Button-1>", lambda _event: self._toggle_indicators_popup())

        self._make_chip(left, text="Replay").pack(side="left", padx=(0, 8))

        self.refresh_button = self._make_pill_button(right, text="Refresh", command=self.refresh_data)
        self.refresh_button.pack(side="left", padx=(0, 8))
        self.auto_button = self._make_pill_button(right, text="Auto: Off", command=self._toggle_auto_refresh)
        self.auto_button.pack(side="left", padx=(0, 8))
        self.status_chip = self._make_chip(right, textvariable=self.status_var, dot=True)
        self.status_chip.pack(side="left")
        self._update_timeframe_buttons()
        self._update_chart_mode_buttons()
        self._update_indicators_button()
        self._update_auto_button()

    def _build_main_panel(self, parent: tk.Frame) -> None:
        chart_header = tk.Frame(parent, bg=CHART_HEADER_BG, highlightbackground=BORDER, highlightthickness=1)
        chart_header.grid(row=0, column=0, sticky="ew")

        line_one = tk.Frame(chart_header, bg=CHART_HEADER_BG)
        line_one.pack(fill="x", padx=14, pady=(12, 4))
        tk.Label(line_one, textvariable=self.chart_title_var, bg=CHART_HEADER_BG, fg=CHART_TEXT, font=("Helvetica", 19, "bold")).pack(side="left")
        tk.Label(line_one, textvariable=self.chart_context_var, bg=CHART_HEADER_BG, fg=CHART_TEXT, font=("Helvetica", 14)).pack(side="left", padx=(10, 0))
        tk.Label(line_one, textvariable=self.open_var, bg=CHART_HEADER_BG, fg=CHART_TEXT, font=("Helvetica", 14)).pack(side="left", padx=(14, 0))
        tk.Label(line_one, textvariable=self.high_var, bg=CHART_HEADER_BG, fg=GREEN, font=("Helvetica", 14)).pack(side="left", padx=(10, 0))
        tk.Label(line_one, textvariable=self.low_var, bg=CHART_HEADER_BG, fg=CHART_TEXT, font=("Helvetica", 14)).pack(side="left", padx=(10, 0))
        self.close_label = tk.Label(line_one, textvariable=self.close_var, bg=CHART_HEADER_BG, fg=RED, font=("Helvetica", 14))
        self.close_label.pack(side="left", padx=(10, 0))
        self.change_label = tk.Label(line_one, textvariable=self.change_var, bg=CHART_HEADER_BG, fg=RED, font=("Helvetica", 14))
        self.change_label.pack(side="left", padx=(10, 0))

        line_two = tk.Frame(chart_header, bg=CHART_HEADER_BG)
        line_two.pack(fill="x", padx=14, pady=(0, 10))
        for variable, color in (
            (self.ema_12_var, EMA_12_COLOR),
            (self.ema_144_var, EMA_144_COLOR),
            (self.ema_169_var, EMA_169_COLOR),
            (self.ema_238_var, EMA_238_COLOR),
            (self.ema_338_var, EMA_338_COLOR),
        ):
            tk.Label(line_two, textvariable=variable, bg=CHART_HEADER_BG, fg=color, font=("Helvetica", 11)).pack(side="left", padx=(0, 12))

        chart_shell = tk.Frame(parent, bg=PANEL_BG, highlightbackground=BORDER, highlightthickness=1)
        chart_shell.grid(row=1, column=0, sticky="nsew")
        chart_shell.columnconfigure(0, weight=1)
        chart_shell.rowconfigure(0, weight=1)
        self.chart_mount = tk.Frame(chart_shell, bg=PANEL_BG)
        self.chart_mount.grid(row=0, column=0, sticky="nsew")
        self.chart_mount.columnconfigure(0, weight=1)
        self.chart_mount.rowconfigure(0, weight=1)
        self.chart_widget = TradingChartCanvas(
            self.chart_mount,
            hover_callback=self._apply_hover_index,
            leave_callback=self._restore_latest_chart_state,
        )
        self.chart_widget.set_display_mode(self.chart_mode)
        self.chart_widget.set_selected_indicators(self.selected_indicators)
        self.chart_widget.grid(row=0, column=0, sticky="nsew")

    def _build_sidebar(self, parent: tk.Frame) -> None:
        watch_card = tk.Frame(parent, bg=PANEL_BG, highlightbackground=BORDER, highlightthickness=1)
        watch_card.pack(fill="x")

        card_head = tk.Frame(watch_card, bg=PANEL_BG)
        card_head.pack(fill="x", padx=14, pady=(14, 12))
        head_text = tk.Frame(card_head, bg=PANEL_BG)
        head_text.pack(side="left")
        tk.Label(head_text, text="Watchlist", bg=PANEL_BG, fg=TEXT, font=("Helvetica", 15, "bold")).pack(anchor="w")
        tk.Label(head_text, text="Closest to your reference layout", bg=PANEL_BG, fg=TEXT_DIM, font=("Helvetica", 11)).pack(anchor="w", pady=(4, 0))
        self._make_chip(card_head, text="+ Add").pack(side="right")

        tabs = tk.Frame(watch_card, bg=PANEL_BG)
        tabs.pack(fill="x", padx=14, pady=(0, 8))
        for text, width in (("Symbol", 16), ("Last", 10), ("Chg", 10), ("Chg%", 10)):
            tk.Label(tabs, text=text, bg=PANEL_BG, fg=TEXT_DIM, font=("Helvetica", 10), width=width, anchor="w" if text == "Symbol" else "e").pack(side="left")

        rows_parent = tk.Frame(watch_card, bg=PANEL_BG)
        rows_parent.pack(fill="x", padx=0, pady=(0, 4))
        for symbol in self.settings.monitor.symbols:
            self.watch_rows[symbol] = self._create_watch_row(rows_parent, symbol)

        setup_card = tk.Frame(parent, bg=PANEL_BG, highlightbackground=BORDER, highlightthickness=1)
        setup_card.pack(fill="x", pady=(12, 0))
        head = tk.Frame(setup_card, bg=PANEL_BG)
        head.pack(fill="x", padx=14, pady=(14, 12))
        tk.Label(head, text="Current setup", bg=PANEL_BG, fg=TEXT, font=("Helvetica", 15, "bold")).pack(anchor="w")
        tk.Label(head, text="Assistant panel inside the TV-like shell", bg=PANEL_BG, fg=TEXT_DIM, font=("Helvetica", 11)).pack(anchor="w", pady=(4, 0))

        setup_body = tk.Frame(setup_card, bg=PANEL_BG)
        setup_body.pack(fill="x", padx=14, pady=(0, 10))
        for key, label in (
            ("setup", "Breakdown retest"),
            ("sell", "Sell strength"),
            ("blocked", "Blocked buying"),
            ("imbalance", "Book imbalance"),
            ("invalidation", "Invalidation above"),
        ):
            row = tk.Frame(setup_body, bg="#1b231e")
            row.pack(fill="x", pady=4)
            tk.Label(row, text=label, bg="#1b231e", fg=TEXT_SOFT, font=("Helvetica", 12), padx=12, pady=10).pack(side="left")
            value = tk.Label(row, text="--", bg="#1b231e", fg=TEXT_DIM, font=("Helvetica", 12, "bold"), padx=12, pady=10)
            value.pack(side="right")
            self.setup_value_labels[key] = value

        tk.Label(
            setup_card,
            textvariable=self.setup_note_var,
            bg=PANEL_BG,
            fg=TEXT_DIM,
            font=("Helvetica", 11),
            justify="left",
            wraplength=300,
            padx=14,
            pady=8,
        ).pack(fill="x")

    def _build_bottom_bar(self, parent: tk.Frame) -> None:
        left = tk.Frame(parent, bg=PANEL_BG)
        left.pack(side="left", padx=12, pady=8)
        right = tk.Frame(parent, bg=PANEL_BG)
        right.pack(side="right", padx=12, pady=8)

        for label, active in (("1D", False), ("5D", False), ("1M", True), ("3M", False), ("YTD", False), ("1Y", False), ("All", False)):
            tk.Label(
                left,
                text=label,
                bg="#212a24" if active else "#19201a",
                fg=TEXT if active else TEXT_SOFT,
                font=("Helvetica", 11),
                padx=10,
                pady=6,
            ).pack(side="left", padx=(0, 8))

        tk.Label(right, textvariable=self.bottom_meta_var, bg=PANEL_BG, fg=TEXT_DIM, font=("Helvetica", 11)).pack(side="right")

    def _create_watch_row(self, parent: tk.Frame, symbol: str) -> WatchRowWidgets:
        frame = tk.Frame(parent, bg=PANEL_BG, padx=14, pady=12)
        frame.pack(fill="x")
        frame.configure(highlightbackground=PANEL_BG, highlightthickness=0)

        symbol_frame = tk.Frame(frame, bg=PANEL_BG)
        symbol_frame.pack(side="left", fill="x", expand=True)
        badge_text, badge_bg, badge_fg = _symbol_badge(symbol)
        badge = tk.Label(symbol_frame, text=badge_text, bg=badge_bg, fg=badge_fg, font=("Helvetica", 10, "bold"), width=2, pady=4)
        badge.pack(side="left", padx=(0, 10))
        text_holder = tk.Frame(symbol_frame, bg=PANEL_BG)
        text_holder.pack(side="left")
        primary = tk.Label(text_holder, text=_display_symbol(symbol), bg=PANEL_BG, fg=TEXT, font=("Helvetica", 13, "bold"))
        primary.pack(anchor="w")
        secondary = tk.Label(text_holder, text="Waiting for data", bg=PANEL_BG, fg=TEXT_DIM, font=("Helvetica", 10))
        secondary.pack(anchor="w", pady=(2, 0))

        last_value = tk.Label(frame, text="--", bg=PANEL_BG, fg=TEXT, font=("Helvetica", 12, "bold"), width=11, anchor="e")
        last_value.pack(side="left")
        change_value = tk.Label(frame, text="--", bg=PANEL_BG, fg=TEXT_DIM, font=("Helvetica", 12), width=10, anchor="e")
        change_value.pack(side="left")
        percent_value = tk.Label(frame, text="--", bg=PANEL_BG, fg=TEXT_DIM, font=("Helvetica", 12), width=10, anchor="e")
        percent_value.pack(side="left")

        widgets = [frame, symbol_frame, text_holder, badge, primary, secondary, last_value, change_value, percent_value]
        callback = lambda _event, target=symbol: self._select_symbol(target)
        for widget in widgets:
            widget.bind("<Button-1>", callback)
            if isinstance(widget, tk.Label):
                widget.configure(cursor="hand2")
        frame.bind("<Enter>", lambda _event, target=symbol: self._preview_row(target))
        frame.bind("<Leave>", lambda _event: self._render_watchlist())
        return WatchRowWidgets(frame, primary, secondary, last_value, change_value, percent_value, widgets)

    def _make_chip(
        self,
        parent: tk.Widget,
        *,
        text: str | None = None,
        textvariable: tk.StringVar | None = None,
        badge_symbol: str | None = None,
        badge_bg: str = BLUE,
        active: bool = False,
        dot: bool = False,
    ) -> tk.Frame:
        frame = tk.Frame(parent, bg="#1b231e" if active else "#19201a", highlightbackground="#2b3529", highlightthickness=1)
        inner = tk.Frame(frame, bg=frame["bg"])
        inner.pack(padx=10, pady=6)
        if badge_symbol is not None:
            tk.Label(inner, text=badge_symbol, bg=badge_bg, fg="#ffffff", width=2, font=("Helvetica", 10, "bold")).pack(side="left", padx=(0, 8))
        if dot:
            tk.Label(inner, text="", bg=GREEN, width=1, height=1).pack(side="left", padx=(0, 8))
        label = tk.Label(inner, text=text, textvariable=textvariable, bg=frame["bg"], fg=TEXT if active else TEXT_SOFT, font=("Helvetica", 11))
        label.pack(side="left")
        return frame

    def _make_pill_button(self, parent: tk.Widget, *, text: str, command: object) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg="#19201a",
            fg=TEXT_SOFT,
            activebackground="#212a24",
            activeforeground=TEXT,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground="#2b3529",
            padx=12,
            pady=8,
            font=("Helvetica", 11),
            cursor="hand2",
        )

    def _make_timeframe_button(self, parent: tk.Widget, *, text: str) -> tk.Label:
        return tk.Label(
            parent,
            text=text,
            bg="#19201a",
            fg=TEXT_SOFT,
            padx=16,
            pady=9,
            font=("Helvetica", 11),
            highlightthickness=1,
            highlightbackground="#2b3529",
            cursor="hand2",
        )

    def _set_interval(self, interval: int) -> None:
        self._hovered_timeframe = None
        self._hide_timeframe_tooltip()
        if self.selected_interval == interval:
            self._update_timeframe_buttons()
            return
        self.selected_interval = interval
        self._update_timeframe_buttons()
        self.refresh_data()

    def _show_timeframe_tooltip(self, button: tk.Label, interval: int) -> None:
        self._hide_timeframe_tooltip()
        tooltip = tk.Toplevel(self.root)
        tooltip.overrideredirect(True)
        tooltip.transient(self.root)
        tooltip.configure(bg="#e5ede7", padx=1, pady=1)
        label = tk.Label(
            tooltip,
            text=_format_timeframe_tooltip(interval),
            bg="#e5ede7",
            fg="#101511",
            font=("Helvetica", 10),
            padx=8,
            pady=4,
        )
        label.pack()
        tooltip.update_idletasks()
        x = button.winfo_rootx() + max((button.winfo_width() - tooltip.winfo_width()) // 2, 0)
        y = button.winfo_rooty() + button.winfo_height() + 6
        tooltip.geometry(f"+{x}+{y}")
        self._timeframe_tooltip = tooltip

    def _hide_timeframe_tooltip(self) -> None:
        if self._timeframe_tooltip is not None:
            self._timeframe_tooltip.destroy()
            self._timeframe_tooltip = None

    def _on_timeframe_hover_enter(self, interval: int, button: tk.Label) -> None:
        self._hovered_timeframe = interval
        self._update_timeframe_buttons()
        self._show_timeframe_tooltip(button, interval)

    def _on_timeframe_hover_leave(self, interval: int) -> None:
        if self._hovered_timeframe == interval:
            self._hovered_timeframe = None
        self._hide_timeframe_tooltip()
        self._update_timeframe_buttons()

    def _select_symbol(self, symbol: str) -> None:
        self.selected_symbol = symbol
        self.symbol_chip_var.set(_display_symbol(symbol))
        self._render_watchlist()
        bundle = self.current_bundles.get(symbol)
        if bundle is not None:
            self._render_bundle(bundle)

    def _set_chart_mode(self, mode: str) -> None:
        if self.chart_mode == mode:
            return
        self.chart_mode = mode
        self._update_chart_mode_buttons()
        if self.chart_widget is not None:
            self.chart_widget.set_display_mode(mode)

    def _toggle_indicators_popup(self) -> None:
        if self._indicators_popup is not None and self._indicators_popup.winfo_exists():
            self._hide_indicators_popup()
        else:
            self._show_indicators_popup()

    def _show_indicators_popup(self) -> None:
        if self.indicators_button is None:
            return
        self._hide_indicators_popup()
        popup = tk.Toplevel(self.root)
        popup.transient(self.root)
        popup.configure(bg="#0e130f", padx=1, pady=1)
        popup.overrideredirect(True)

        body = tk.Frame(popup, bg="#131814")
        body.pack(fill="both", expand=True)
        tk.Label(
            body,
            text="Indicators",
            bg="#131814",
            fg=TEXT,
            font=("Helvetica", 11, "bold"),
            padx=12,
            pady=10,
            anchor="w",
        ).pack(fill="x")

        self.indicator_row_widgets = {}
        for key, label in INDICATOR_OPTIONS:
            row = tk.Frame(body, bg="#131814")
            row.pack(fill="x", padx=8, pady=(0, 6))
            title = tk.Label(row, text=label, bg="#131814", fg=TEXT_SOFT, font=("Helvetica", 11), padx=12, pady=10, anchor="w")
            title.pack(fill="x")
            widgets: list[tk.Widget] = [row, title]
            self.indicator_row_widgets[key] = widgets
            for widget in widgets:
                widget.bind("<Button-1>", lambda _event, value=key: self._toggle_indicator(value))
            row.bind("<Enter>", lambda _event, value=key: self._update_indicator_row_style(value, hovered=True))
            row.bind("<Leave>", lambda _event, value=key: self._update_indicator_row_style(value, hovered=False))
            title.bind("<Enter>", lambda _event, value=key: self._update_indicator_row_style(value, hovered=True))
            title.bind("<Leave>", lambda _event, value=key: self._update_indicator_row_style(value, hovered=False))

        popup.update_idletasks()
        x = self.indicators_button.winfo_rootx()
        y = self.indicators_button.winfo_rooty() + self.indicators_button.winfo_height() + 6
        popup.geometry(f"+{x}+{y}")
        popup.bind("<Escape>", lambda _event: self._hide_indicators_popup())
        self._indicators_popup = popup
        self._refresh_indicator_rows()
        self._update_indicators_button()

    def _hide_indicators_popup(self) -> None:
        if self._indicators_popup is not None:
            self._indicators_popup.destroy()
            self._indicators_popup = None
        self.indicator_row_widgets = {}
        self._update_indicators_button()

    def _handle_global_click(self, event: tk.Event[tk.Misc]) -> None:
        if self._indicators_popup is None or not self._indicators_popup.winfo_exists():
            return
        widget = event.widget
        if self._widget_is_descendant(widget, self._indicators_popup):
            return
        if self.indicators_button is not None and self._widget_is_descendant(widget, self.indicators_button):
            return
        self._hide_indicators_popup()

    def _widget_is_descendant(self, widget: tk.Misc, target: tk.Misc) -> bool:
        current: tk.Misc | None = widget
        while current is not None:
            if current == target:
                return True
            current = current.master
        return False

    def _toggle_indicator(self, key: str) -> None:
        if key in self.selected_indicators:
            self.selected_indicators = [indicator for indicator in self.selected_indicators if indicator != key]
        else:
            self.selected_indicators.append(key)
        if self.chart_widget is not None:
            self.chart_widget.set_selected_indicators(self.selected_indicators)
        self._refresh_indicator_rows()
        self._update_indicators_button()
        if self.current_bundle is not None:
            self._set_default_bottom_meta()

    def _refresh_indicator_rows(self) -> None:
        for key in self.indicator_row_widgets:
            self._update_indicator_row_style(key, hovered=False)

    def _update_indicator_row_style(self, key: str, *, hovered: bool) -> None:
        widgets = self.indicator_row_widgets.get(key)
        if not widgets:
            return
        selected = key in self.selected_indicators
        bg = "#212a24" if selected else "#1f2822" if hovered else "#131814"
        fg = TEXT if selected or hovered else TEXT_SOFT
        for widget in widgets:
            widget.configure(bg=bg)
            if isinstance(widget, tk.Label):
                widget.configure(fg=fg)

    def _update_indicators_button(self) -> None:
        if self.indicators_button is None:
            return
        popup_open = self._indicators_popup is not None and self._indicators_popup.winfo_exists()
        active = popup_open or bool(self.selected_indicators)
        self.indicators_button.configure(
            bg="#212a24" if active else "#19201a",
            fg=TEXT if active else TEXT_SOFT,
            highlightbackground="#2b3529",
        )

    def _preview_row(self, symbol: str) -> None:
        if symbol == self.selected_symbol:
            return
        row = self.watch_rows.get(symbol)
        if row is None:
            return
        for widget in row.widgets:
            widget.configure(bg="#19201a")

    def refresh_data(self) -> None:
        if self._loading:
            return
        self._loading = True
        interval_label = format_timeframe_label(self.selected_interval)
        self.status_var.set(f"Refreshing Kraken {interval_label} snapshot…")
        self.bottom_meta_var.set(f"Refreshing {interval_label} data for {len(self.settings.monitor.symbols)} markets…")

        def worker() -> None:
            try:
                bundles = collect_market_bundles(
                    self.settings,
                    self.store,
                    self.alert_manager,
                    symbols=self.settings.monitor.symbols,
                    intervals=[self.selected_interval],
                )
                if not bundles:
                    raise RuntimeError("No market bundles were returned for the selected timeframe.")
                self._queue.put(("data", bundles))
            except Exception as exc:
                self._queue.put(("error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _drain_queue(self) -> None:
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                self._loading = False
                if kind == "data":
                    self._apply_bundles(payload)  # type: ignore[arg-type]
                else:
                    message = f"Refresh failed: {payload}"
                    self.status_var.set(message)
                    self.bottom_meta_var.set(message)
        except queue.Empty:
            pass
        finally:
            self.root.after(250, self._drain_queue)

    def _apply_bundles(self, bundles: list[MonitorBundle]) -> None:
        self.current_bundles = {bundle.symbol: bundle for bundle in bundles}
        if self.selected_symbol not in self.current_bundles:
            self.selected_symbol = bundles[0].symbol
            self.symbol_chip_var.set(_display_symbol(self.selected_symbol))

        self._render_watchlist()
        self._render_bundle(self.current_bundles[self.selected_symbol])
        self.status_var.set(f"Kraken public · {format_timeframe_label(self.selected_interval)} updated")
        self._set_default_bottom_meta()

    def _render_bundle(self, bundle: MonitorBundle) -> None:
        self.current_bundle = bundle
        self._render_chart(bundle)
        self._render_chart_header(bundle)
        self._render_setup_card(bundle)

    def _render_chart(self, bundle: MonitorBundle) -> None:
        if self.chart_widget is None:
            return
        self.chart_widget.set_bundle(bundle)

    def _render_chart_header(self, bundle: MonitorBundle) -> None:
        summary = summarize_market_chart(bundle)
        self.chart_title_var.set(_display_market_name(bundle.symbol))
        self.chart_context_var.set(f"{format_timeframe_label(bundle.interval_minutes)}  Kraken public")
        self._apply_chart_summary(summary)

    def _render_watchlist(self) -> None:
        for symbol, row in self.watch_rows.items():
            bundle = self.current_bundles.get(symbol)
            selected = symbol == self.selected_symbol
            bg = "#1e2b22" if selected else PANEL_BG
            border = "#2b3529" if selected else PANEL_BG
            for widget in row.widgets:
                widget.configure(bg=bg)
            row.frame.configure(highlightbackground=border, highlightthickness=1 if selected else 0)

            if bundle is None:
                row.symbol_secondary.configure(text="Waiting for data", fg=TEXT_DIM)
                row.last_value.configure(text="--", fg=TEXT_DIM)
                row.change_value.configure(text="--", fg=TEXT_DIM)
                row.percent_value.configure(text="--", fg=TEXT_DIM)
                continue

            last_close = float(bundle.candles[-1].close)
            previous_close = float(bundle.candles[-2].close) if len(bundle.candles) > 1 else last_close
            change = last_close - previous_close
            percent = (change / previous_close * 100) if previous_close else 0.0
            change_text, percent_text = _format_change(change, percent)
            signal = bundle.analysis.signal
            row.symbol_secondary.configure(
                text=signal.setup_name if signal is not None else "Monitoring",
                fg=TEXT_DIM,
            )
            row.last_value.configure(text=_format_price(last_close), fg=TEXT)
            change_color = GREEN if change >= 0 else RED
            row.change_value.configure(text=change_text, fg=change_color)
            row.percent_value.configure(text=percent_text, fg=change_color)

    def _render_setup_card(self, bundle: MonitorBundle) -> None:
        signal = bundle.analysis.signal
        response = bundle.analysis.response
        signal_text = signal.setup_name if signal is not None else "No active setup"
        self.setup_value_labels["setup"].configure(text=signal_text, fg=RED if signal is not None else TEXT_DIM)
        self.setup_value_labels["sell"].configure(text=f"{bundle.analysis.trade_flow.sell_strength:.2f}", fg=RED)
        self.setup_value_labels["blocked"].configure(text=f"{response.blocked_buying_score:.2f}", fg=ORANGE)
        imbalance_color = RED if bundle.analysis.book_imbalance < 0 else GREEN
        self.setup_value_labels["imbalance"].configure(text=f"{bundle.analysis.book_imbalance:.2f}", fg=imbalance_color)
        invalidation = signal.invalidation_level if signal is not None else "--"
        self.setup_value_labels["invalidation"].configure(text=str(invalidation), fg=TEXT_DIM)
        if signal is None:
            self.setup_note_var.set("No structured bearish setup is active right now. The assistant is still monitoring price, flow, and book response.")
        else:
            self.setup_note_var.set(signal.notes)

    def _apply_chart_summary(self, summary: object) -> None:
        chart_summary = summary
        self.open_var.set(f"Open {_format_price(chart_summary.open_price)}")
        self.high_var.set(f"High {_format_price(chart_summary.high_price)}")
        self.low_var.set(f"Low {_format_price(chart_summary.low_price)}")
        self.close_var.set(f"Close {_format_price(chart_summary.close_price)}")
        _, percent_text = _format_change(chart_summary.price_change, chart_summary.percent_change)
        self.change_var.set(percent_text)
        change_color = GREEN if chart_summary.price_change >= 0 else RED
        self.close_label.configure(fg=change_color)
        self.change_label.configure(fg=change_color)
        self.ema_12_var.set(f"EMA 12 {_format_price(chart_summary.ema_12)}")
        self.ema_144_var.set(f"EMA 144 {_format_price(chart_summary.ema_144)}")
        self.ema_169_var.set(f"EMA 169 {_format_price(chart_summary.ema_169)}")
        self.ema_238_var.set(f"EMA 238 {_format_price(chart_summary.ema_238)}")
        self.ema_338_var.set(f"EMA 338 {_format_price(chart_summary.ema_338)}")

    def _update_timeframe_buttons(self) -> None:
        for interval, button in self.timeframe_buttons.items():
            active = interval == self.selected_interval
            hovered = interval == self._hovered_timeframe
            button.configure(
                bg="#1f2822" if hovered and not active else "#212a24" if active else "#19201a",
                fg=TEXT if active or hovered else TEXT_SOFT,
                highlightbackground="#2b3529",
            )

    def _update_chart_mode_buttons(self) -> None:
        for mode, button in self.chart_mode_buttons.items():
            active = mode == self.chart_mode
            button.configure(
                bg="#212a24" if active else "#19201a",
                fg=TEXT if active else TEXT_SOFT,
                highlightbackground="#2b3529",
            )

    def _toggle_auto_refresh(self) -> None:
        self.auto_refresh_var.set(not self.auto_refresh_var.get())
        self._update_auto_button()
        self._reschedule_auto_refresh()

    def _update_auto_button(self) -> None:
        if self.auto_button is None:
            return
        enabled = self.auto_refresh_var.get()
        self.auto_button.configure(
            text="Auto: On" if enabled else "Auto: Off",
            bg="#212a24" if enabled else "#19201a",
            fg=TEXT if enabled else TEXT_SOFT,
        )

    def _reschedule_auto_refresh(self) -> None:
        if self._auto_refresh_job is not None:
            self.root.after_cancel(self._auto_refresh_job)
            self._auto_refresh_job = None
        if not self.auto_refresh_var.get():
            return
        refresh_seconds = max(5, self.settings.monitor.poll_seconds)
        self._auto_refresh_job = self.root.after(refresh_seconds * 1000, self._auto_refresh_tick)

    def _auto_refresh_tick(self) -> None:
        self._auto_refresh_job = None
        if self.auto_refresh_var.get():
            self.refresh_data()
            self._reschedule_auto_refresh()

    def _set_default_bottom_meta(self) -> None:
        resize_hint = " · Drag divider to resize panes" if self.selected_indicators else ""
        self.bottom_meta_var.set(
            f"Drag chart to pan · Scroll to zoom{resize_hint} · {format_timeframe_label(self.selected_interval)} · Last update successful"
        )

    def _apply_hover_index(self, candle_index: int | None) -> None:
        if self.current_bundle is None:
            return
        if candle_index is None:
            self._restore_latest_chart_state()
            return
        summary = summarize_market_chart(self.current_bundle, candle_index=candle_index)
        candle = self.current_bundle.candles[candle_index]
        timestamp = candle.open_time.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
        self.chart_context_var.set(f"{format_timeframe_label(self.current_bundle.interval_minutes)}  {timestamp}")
        self._apply_chart_summary(summary)
        resize_hint = " · Drag divider to resize panes" if self.selected_indicators else ""
        self.bottom_meta_var.set(f"Viewing {timestamp} · Drag to pan · Scroll to zoom{resize_hint}")

    def _restore_latest_chart_state(self) -> None:
        if self.current_bundle is None:
            return
        self.chart_context_var.set(f"{format_timeframe_label(self.current_bundle.interval_minutes)}  Kraken public")
        self._apply_chart_summary(summarize_market_chart(self.current_bundle))
        self._set_default_bottom_meta()


def main() -> None:
    root = tk.Tk()
    app = TradingAssistantApp(root)
    app._reschedule_auto_refresh()
    root.mainloop()


if __name__ == "__main__":
    main()
