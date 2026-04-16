"""Lightweight interactive chart canvas for the desktop dashboard."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC
import math
import tkinter as tk

from features.footprint import CandleFootprint
from services.monitor import MonitorBundle
from ui.charts import EMA_12_COLOR, EMA_144_COLOR, EMA_169_COLOR, EMA_238_COLOR, EMA_338_COLOR


PRICE_UP = "#22ab94"
PRICE_DOWN = "#f23645"
OSC_FAST = "#6f63ff"
OSC_SLOW = "#ffcb2f"
BG_PRICE = "#d3e9cf"
BG_OSC = "#cfe6c9"
TEXT = "#20242a"
TEXT_DIM = "#66717d"
PRICE_LABEL_BG = "#1faa8f"
PRICE_LABEL_FG = "#ffffff"
ZOOM_IN_FACTOR = 0.95
ZOOM_OUT_FACTOR = 1.05


def _format_price(value: float) -> str:
    return f"{value:,.2f}"


def _format_interval_label(interval_minutes: int) -> str:
    if interval_minutes < 60:
        return f"{interval_minutes}m"
    return f"{interval_minutes // 60}h"


def _format_compact_volume(value: float) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return f"{value:.0f}"


def _blend_color(base: str, accent: str, weight: float) -> str:
    weight = max(0.0, min(weight, 1.0))
    base_rgb = tuple(int(base[index:index + 2], 16) for index in (1, 3, 5))
    accent_rgb = tuple(int(accent[index:index + 2], 16) for index in (1, 3, 5))
    mixed = tuple(
        round(base_value + (accent_value - base_value) * weight)
        for base_value, accent_value in zip(base_rgb, accent_rgb, strict=True)
    )
    return "#" + "".join(f"{channel:02x}" for channel in mixed)


def _ema(values: list[float], span: int) -> list[float]:
    if not values:
        return []
    alpha = 2 / (span + 1)
    ema_values = [values[0]]
    for value in values[1:]:
        ema_values.append((alpha * value) + ((1 - alpha) * ema_values[-1]))
    return ema_values


class TradingChartCanvas(tk.Canvas):
    def __init__(
        self,
        master: tk.Widget,
        *,
        hover_callback: Callable[[int | None], None] | None = None,
        leave_callback: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master, bg=BG_PRICE, highlightthickness=0, bd=0)
        self.hover_callback = hover_callback
        self.leave_callback = leave_callback
        self.bundle: MonitorBundle | None = None
        self.footprints: list[CandleFootprint] = []
        self.closes: list[float] = []
        self.ema_12: list[float] = []
        self.ema_144: list[float] = []
        self.ema_169: list[float] = []
        self.ema_238: list[float] = []
        self.ema_338: list[float] = []
        self.display_mode = "candles"
        self.selected_indicators: list[str] = ["delta", "bid_ask"]
        self.indicator_area_height = 180.0
        self.view_left = 0.0
        self.view_count = 84.0
        self._drag_start_x: int | None = None
        self._drag_start_view_left: float | None = None
        self._resizing_divider = False
        self._hover_index: int | None = None
        self._hover_x: float | None = None
        self._hover_y: float | None = None
        self._redraw_job: str | None = None

        self.bind("<Configure>", lambda _event: self._schedule_redraw())
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", self._on_leave)
        self.bind("<MouseWheel>", self._on_wheel)
        self.bind("<Button-4>", lambda _event: self._zoom_at(self.winfo_pointerx() - self.winfo_rootx(), ZOOM_IN_FACTOR))
        self.bind("<Button-5>", lambda _event: self._zoom_at(self.winfo_pointerx() - self.winfo_rootx(), ZOOM_OUT_FACTOR))

    def set_bundle(self, bundle: MonitorBundle) -> None:
        self.bundle = bundle
        self.footprints = bundle.candle_footprints
        self.closes = [float(candle.close) for candle in bundle.candles]
        self.ema_12 = _ema(self.closes, 12)
        self.ema_144 = _ema(self.closes, 144)
        self.ema_169 = _ema(self.closes, 169)
        self.ema_238 = _ema(self.closes, 238)
        self.ema_338 = _ema(self.closes, 338)
        self._hover_index = None
        self._hover_x = None
        self._hover_y = None
        self._reset_view()
        self._apply_default_view_for_mode()
        self._schedule_redraw()

    def set_display_mode(self, mode: str) -> None:
        if mode not in {"candles", "footprint"}:
            return
        if self.display_mode == mode:
            return
        self.display_mode = mode
        self._apply_default_view_for_mode()
        self._schedule_redraw()

    def set_selected_indicators(self, indicators: list[str]) -> None:
        previous = set(self.selected_indicators)
        self.selected_indicators = list(dict.fromkeys(indicators))
        if self.selected_indicators:
            self.indicator_area_height = max(self.indicator_area_height, 120.0)
        if "delta" in self.selected_indicators and "delta" not in previous:
            self._focus_trade_coverage()
        self._schedule_redraw()

    def _focus_trade_coverage(self) -> None:
        if self.bundle is None:
            return
        traded_indices = [
            index
            for index, point in enumerate(self.bundle.candle_feature_series)
            if point.trade_count > 0
        ]
        if not traded_indices:
            return

        start = traded_indices[0]
        end = traded_indices[-1]
        span = max(end - start + 1, 1)
        target_count = max(28.0, min(64.0, span * 2.4))
        right_offset = max(4.0, target_count * 0.14)
        center = (start + end) / 2
        target_left = center - target_count / 2 + right_offset * 0.35

        self.view_count = min(target_count, float(len(self.bundle.candles)) + 40.0)
        self.view_left = self._clamp_view_left(target_left)

    def _apply_default_view_for_mode(self) -> None:
        if self.bundle is None:
            return
        if self.display_mode == "footprint" and self.view_count > 12:
            right_edge = self.view_left + self.view_count
            self.view_count = 12.0
            self.view_left = self._clamp_view_left(right_edge - self.view_count)

    def _reset_view(self) -> None:
        if self.bundle is None:
            return
        self.view_count = float(min(max(len(self.bundle.candles), 40), 84))
        right_offset = max(self.view_count * 0.12, 6.0)
        self.view_left = max(0.0, len(self.bundle.candles) - self.view_count + right_offset)
        self.view_left = min(self.view_left, self._max_view_left())

    def _plot_geometry(self) -> tuple[float, float, float, float, float, float]:
        width = max(self.winfo_width(), 640)
        height = max(self.winfo_height(), 420)
        left = 18.0
        right = width - 92.0
        top = 24.0
        bottom = height - 26.0
        indicator_height = min(self.indicator_area_height, height * 0.5) if self.selected_indicators else 0.0
        indicator_top = bottom - indicator_height if indicator_height > 0 else bottom
        return left, right, top, indicator_top, bottom, height

    def _candle_space(self) -> float:
        left, right, *_ = self._plot_geometry()
        plot_width = max(right - left, 1.0)
        return plot_width / max(self.view_count, 1.0)

    def _max_view_left(self) -> float:
        if self.bundle is None:
            return 0.0
        future_space = max(24.0, self.view_count * 0.95)
        return max(0.0, len(self.bundle.candles) - self.view_count + future_space)

    def _clamp_view_left(self, value: float) -> float:
        return max(0.0, min(value, self._max_view_left()))

    def _visible_indices(self) -> list[int]:
        if self.bundle is None:
            return []
        start = max(0, int(math.floor(self.view_left)) - 1)
        end = min(len(self.bundle.candles) - 1, int(math.ceil(self.view_left + self.view_count)) + 1)
        return list(range(start, end + 1))

    def _actual_visible_indices(self) -> list[int]:
        if self.bundle is None:
            return []
        left_edge = self.view_left
        right_edge = self.view_left + self.view_count
        return [
            index
            for index in range(len(self.bundle.candles))
            if left_edge <= index <= right_edge
        ]

    def _x_from_index(self, index: float) -> float:
        left, _, _, _, _, _ = self._plot_geometry()
        return left + ((index - self.view_left) + 0.5) * self._candle_space()

    def _index_from_x(self, x: float) -> int | None:
        if self.bundle is None:
            return None
        left, right, _, _, _, _ = self._plot_geometry()
        if x < left or x > right:
            return None
        index = int(round(self.view_left + ((x - left) / self._candle_space()) - 0.5))
        if 0 <= index < len(self.bundle.candles):
            return index
        return None

    def _schedule_redraw(self) -> None:
        if self._redraw_job is not None:
            return
        self._redraw_job = self.after_idle(self._redraw)

    def _plot_contains_point(self, x: float, y: float) -> bool:
        left, right, top, _, bottom, _ = self._plot_geometry()
        return left <= x <= right and top <= y <= bottom

    def _divider_hit(self, y: float) -> bool:
        if not self.selected_indicators:
            return False
        _, _, _, indicator_top, _, _ = self._plot_geometry()
        return abs(y - indicator_top) <= 6

    def _notify_hover(self, index: int | None) -> None:
        if self.hover_callback is not None:
            self.hover_callback(index)

    def _draw_text_box(
        self,
        x: float,
        y: float,
        text: str,
        *,
        anchor: str,
        fill: str,
        bg: str,
        outline: str = "",
        font: tuple[str, int, str] | tuple[str, int] = ("Helvetica", 10),
        pad_x: int = 8,
        pad_y: int = 4,
    ) -> None:
        text_id = self.create_text(x, y, text=text, anchor=anchor, fill=fill, font=font)
        x0, y0, x1, y1 = self.bbox(text_id)
        rect_id = self.create_rectangle(x0 - pad_x, y0 - pad_y, x1 + pad_x, y1 + pad_y, fill=bg, outline=outline)
        self.tag_raise(text_id, rect_id)

    def _draw_delta_indicator(
        self,
        visible_indices: list[int],
        *,
        left: float,
        right: float,
        pane_top: float,
        pane_bottom: float,
        body_width: float,
    ) -> None:
        if self.bundle is None:
            return
        series = self.bundle.candle_feature_series
        values = [series[index].normalized_delta * 100 for index in visible_indices]
        covered_indices = [index for index in visible_indices if series[index].trade_count > 0]
        max_abs = max((abs(value) for value in values), default=10.0)
        max_abs = max(max_abs, 10.0)
        mid_y = (pane_top + pane_bottom) / 2
        self.create_line(left, mid_y, right, mid_y, fill="#b7c2b1", dash=(4, 6))
        self.create_text(left, pane_top + 10, text="Delta", anchor="nw", fill=TEXT_DIM, font=("Helvetica", 10))
        self.create_text(
            right,
            pane_top + 10,
            text=f"{len(covered_indices)}/{len(visible_indices)} candles covered",
            anchor="ne",
            fill=TEXT_DIM,
            font=("Helvetica", 9),
        )

        if not covered_indices:
            self.create_text(
                (left + right) / 2,
                (pane_top + pane_bottom) / 2,
                text="No captured trades in current view",
                anchor="center",
                fill=TEXT_DIM,
                font=("Helvetica", 11),
            )
            return

        usable_height = max((pane_bottom - pane_top) / 2 - 18, 1.0)
        for index in visible_indices:
            value = series[index].normalized_delta * 100
            if series[index].trade_count <= 0:
                continue
            x = self._x_from_index(index)
            bar_height = (abs(value) / max_abs) * usable_height
            color = PRICE_UP if value >= 0 else PRICE_DOWN
            self.create_rectangle(
                x - body_width / 2,
                mid_y - bar_height if value >= 0 else mid_y,
                x + body_width / 2,
                mid_y if value >= 0 else mid_y + bar_height,
                fill=color,
                outline="",
            )

    def _draw_bid_ask_indicator(
        self,
        *,
        left: float,
        right: float,
        pane_top: float,
        pane_bottom: float,
    ) -> None:
        if self.bundle is None:
            return
        indicator = self.bundle.analysis.bid_ask_indicator
        self.create_text(left, pane_top + 10, text="Bid/Ask", anchor="nw", fill=TEXT_DIM, font=("Helvetica", 10))
        if indicator is None:
            self.create_text(left + 80, (pane_top + pane_bottom) / 2, text="No book snapshot", anchor="w", fill=TEXT_DIM, font=("Helvetica", 11))
            return

        center_x = (left + right) / 2
        gauge_y = pane_top + 42
        gauge_height = 16
        gauge_half_width = min((right - left) * 0.32, 180.0)
        imbalance = indicator.top_of_book_imbalance
        fill_width = gauge_half_width * abs(imbalance)

        self.create_rectangle(center_x - gauge_half_width, gauge_y, center_x + gauge_half_width, gauge_y + gauge_height, fill="#dfe7da", outline="#b7c2b1")
        self.create_line(center_x, gauge_y - 4, center_x, gauge_y + gauge_height + 4, fill="#8ea08b")
        if imbalance >= 0:
            self.create_rectangle(center_x, gauge_y + 1, center_x + fill_width, gauge_y + gauge_height - 1, fill=PRICE_UP, outline="")
        else:
            self.create_rectangle(center_x - fill_width, gauge_y + 1, center_x, gauge_y + gauge_height - 1, fill=PRICE_DOWN, outline="")

        bid_text = f"Bid {float(indicator.best_bid_volume):.2f}"
        ask_text = f"Ask {float(indicator.best_ask_volume):.2f}"
        ratio_text = (
            f"Ratio {indicator.bid_ask_volume_ratio:.2f}x"
            if indicator.bid_ask_volume_ratio is not None
            else "Ratio N/A"
        )
        spread_text = f"Spread {float(indicator.spread):.2f} / {indicator.spread_bps:.2f}bps"

        self.create_text(left, pane_bottom - 16, text=bid_text, anchor="sw", fill=GREEN, font=("Helvetica", 10, "bold"))
        self.create_text(center_x, pane_bottom - 16, text=ratio_text, anchor="s", fill=TEXT, font=("Helvetica", 10))
        self.create_text(right, pane_bottom - 16, text=ask_text, anchor="se", fill=RED, font=("Helvetica", 10, "bold"))
        self.create_text(center_x, gauge_y + gauge_height + 14, text=spread_text, anchor="n", fill=TEXT_DIM, font=("Helvetica", 9))

    def _draw_indicator_panes(
        self,
        visible_indices: list[int],
        *,
        left: float,
        right: float,
        indicator_top: float,
        bottom: float,
        body_width: float,
        width: float,
    ) -> None:
        if not self.selected_indicators:
            return
        self.create_rectangle(0, indicator_top, width, bottom + 8, fill=BG_OSC, outline="")
        self.create_line(0, indicator_top, width, indicator_top, fill="#a8b7a2", width=1)
        pane_count = len(self.selected_indicators)
        pane_height = (bottom - indicator_top) / max(pane_count, 1)

        for pane_index, indicator_name in enumerate(self.selected_indicators):
            pane_top = indicator_top + pane_index * pane_height
            pane_bottom = indicator_top + (pane_index + 1) * pane_height
            if pane_index > 0:
                self.create_line(0, pane_top, width, pane_top, fill="#b7c2b1", width=1)
            if indicator_name == "delta":
                self._draw_delta_indicator(
                    visible_indices,
                    left=left,
                    right=right,
                    pane_top=pane_top,
                    pane_bottom=pane_bottom,
                    body_width=body_width,
                )
            elif indicator_name == "bid_ask":
                self._draw_bid_ask_indicator(
                    left=left,
                    right=right,
                    pane_top=pane_top,
                    pane_bottom=pane_bottom,
                )

    def _draw_candles(
        self,
        visible_indices: list[int],
        *,
        y_price: Callable[[float], float],
        body_width: float,
        price_bottom: float,
        max_volume: float,
        volume_height: float,
    ) -> None:
        if self.bundle is None:
            return
        for index in visible_indices:
            candle = self.bundle.candles[index]
            x = self._x_from_index(index)
            open_price = float(candle.open)
            high_price = float(candle.high)
            low_price = float(candle.low)
            close_price = float(candle.close)
            color = PRICE_UP if close_price >= open_price else PRICE_DOWN
            y_open = y_price(open_price)
            y_close = y_price(close_price)
            y_high = y_price(high_price)
            y_low = y_price(low_price)
            body_top = min(y_open, y_close)
            body_bottom = max(y_open, y_close)
            if body_bottom - body_top < 2:
                body_bottom = body_top + 2

            self.create_line(x, y_high, x, y_low, fill=color, width=2)
            self.create_rectangle(
                x - body_width / 2,
                body_top,
                x + body_width / 2,
                body_bottom,
                fill=color,
                outline=color,
            )

            volume = float(candle.volume)
            bar_height = (volume / max_volume) * volume_height if max_volume else 0.0
            self.create_rectangle(
                x - body_width / 2,
                price_bottom - 10 - bar_height,
                x + body_width / 2,
                price_bottom - 10,
                fill="#a4ddd1" if close_price >= open_price else "#e8c6c0",
                outline="",
            )

    def _draw_footprints(
        self,
        visible_indices: list[int],
        *,
        y_price: Callable[[float], float],
        body_width: float,
        price_bottom: float,
        max_volume: float,
        volume_height: float,
    ) -> None:
        if self.bundle is None:
            return
        neutral_bg = "#dfe7da"
        outline = "#8ea08b"
        for index in visible_indices:
            candle = self.bundle.candles[index]
            footprint = self.footprints[index] if index < len(self.footprints) else None
            x = self._x_from_index(index)
            high_y = y_price(float(candle.high))
            low_y = y_price(float(candle.low))
            open_y = y_price(float(candle.open))
            close_y = y_price(float(candle.close))
            box_width = min(max(body_width * 1.08, 14.0), max(self._candle_space() * 0.82, 14.0))
            half_width = box_width / 2
            left_x = x - half_width
            right_x = x + half_width
            mid_x = x

            buy_ratio = footprint.buy_ratio if footprint is not None else 0.0
            sell_ratio = footprint.sell_ratio if footprint is not None else 0.0
            delta = footprint.normalized_delta if footprint is not None else 0.0
            trade_count = footprint.trade_count if footprint is not None else 0

            border_color = _blend_color(outline, PRICE_UP if delta >= 0 else PRICE_DOWN, 0.35)

            has_price_levels = footprint is not None and len(footprint.price_levels) >= 2
            can_render_cells = has_price_levels and box_width >= 34
            if can_render_cells:
                self.create_rectangle(left_x, high_y, right_x, low_y, fill="", outline=border_color, width=1)
                max_level_volume = max(float(level.total_volume) for level in footprint.price_levels)
                for level in footprint.price_levels:
                    row_top = y_price(float(min(level.upper_price, candle.high)))
                    row_bottom = y_price(float(max(level.lower_price, candle.low)))
                    if row_bottom - row_top < 2:
                        row_bottom = row_top + 2

                    level_scale = (float(level.total_volume) / max_level_volume) if max_level_volume else 0.0
                    sell_fill = _blend_color(neutral_bg, PRICE_DOWN, 0.06 + level_scale * 0.12 + abs(min(level.normalized_delta, 0.0)) * 0.34)
                    buy_fill = _blend_color(neutral_bg, PRICE_UP, 0.06 + level_scale * 0.12 + max(level.normalized_delta, 0.0) * 0.34)

                    self.create_rectangle(left_x + 1, row_top, mid_x, row_bottom, fill=sell_fill, outline="")
                    self.create_rectangle(mid_x, row_top, right_x - 1, row_bottom, fill=buy_fill, outline="")
                    self.create_line(left_x + 1, row_bottom, right_x - 1, row_bottom, fill="#c9d5c4", width=1)

                    if box_width >= 24 and row_bottom - row_top >= 9:
                        self.create_text(
                            mid_x - 4,
                            (row_top + row_bottom) / 2,
                            text=_format_compact_volume(float(level.sell_volume)),
                            anchor="e",
                            fill=TEXT,
                            font=("Helvetica", 6, "bold"),
                        )
                        self.create_text(
                            mid_x + 4,
                            (row_top + row_bottom) / 2,
                            text=_format_compact_volume(float(level.buy_volume)),
                            anchor="w",
                            fill=TEXT,
                            font=("Helvetica", 6, "bold"),
                        )
                self.create_line(mid_x, high_y + 2, mid_x, low_y - 2, fill=border_color, width=1)
                self.create_line(left_x, open_y, right_x, open_y, fill="#4e575f", width=1)
                self.create_line(left_x, close_y, right_x, close_y, fill=PRICE_UP if float(candle.close) >= float(candle.open) else PRICE_DOWN, width=2)

                if box_width >= 28 and trade_count > 0:
                    self.create_text(
                        x,
                        high_y - 8,
                        text=f"{int(round(delta * 100)):+d}",
                        fill=TEXT,
                        font=("Helvetica", 8, "bold"),
                    )
            else:
                # If the candle is too narrow or lacks enough price levels, render a simple
                # outline instead of a misleading footprint block.
                body_left = x - max(body_width * 0.42, 2.0)
                body_right = x + max(body_width * 0.42, 2.0)
                candle_color = PRICE_UP if float(candle.close) >= float(candle.open) else PRICE_DOWN
                self.create_line(x, high_y, x, low_y, fill="#91a296", width=1)
                self.create_rectangle(
                    body_left,
                    min(open_y, close_y),
                    body_right,
                    max(open_y, close_y) if abs(close_y - open_y) >= 2 else min(open_y, close_y) + 2,
                    fill="",
                    outline=_blend_color("#9fb3aa", candle_color, 0.45),
                    width=1,
                )

            volume = float(footprint.total_volume) if footprint is not None and float(footprint.total_volume) > 0 else float(candle.volume)
            bar_height = (volume / max_volume) * volume_height if max_volume else 0.0
            volume_color = _blend_color("#dfe7da", PRICE_UP if delta >= 0 else PRICE_DOWN, 0.38)
            self.create_rectangle(
                x - body_width / 2,
                price_bottom - 10 - bar_height,
                x + body_width / 2,
                price_bottom - 10,
                fill=volume_color,
                outline="",
            )

    def _redraw(self) -> None:
        self._redraw_job = None
        self.delete("all")
        if self.bundle is None or not self.bundle.candles:
            return

        left, right, top, indicator_top, bottom, height = self._plot_geometry()
        price_bottom = indicator_top - 10 if self.selected_indicators else bottom
        width = max(self.winfo_width(), 640)

        self.create_rectangle(0, 0, width, price_bottom, fill=BG_PRICE, outline="")

        visible_indices = self._visible_indices()
        actual_visible = self._actual_visible_indices()
        if not actual_visible:
            return

        highs = [float(self.bundle.candles[index].high) for index in actual_visible]
        lows = [float(self.bundle.candles[index].low) for index in actual_visible]
        min_price = min(lows)
        max_price = max(highs)
        price_range = max(max_price - min_price, 1.0)
        y_pad_top = price_range * 0.14
        y_pad_bottom = price_range * 0.18
        scale_top = max_price + y_pad_top
        scale_bottom = min_price - y_pad_bottom
        scale_range = max(scale_top - scale_bottom, 1.0)
        volume_height = 90.0

        def y_price(value: float) -> float:
            usable_height = price_bottom - top - 12
            return top + 12 + (scale_top - value) / scale_range * usable_height

        candle_space = self._candle_space()
        body_width = max(candle_space * 0.62, 2.0)
        if self.display_mode == "footprint" and any(float(footprint.total_volume) > 0 for footprint in self.footprints):
            max_volume = max(float(footprint.total_volume) for footprint in self.footprints)
        else:
            max_volume = max(float(candle.volume) for candle in self.bundle.candles)

        support_level = float(self.bundle.analysis.signal.support_level) if self.bundle.analysis.signal is not None else None
        if support_level is not None:
            y_support = y_price(support_level)
            self.create_line(left, y_support, right, y_support, fill="#6b6f74", width=1)

        if self.display_mode == "footprint":
            self._draw_footprints(
                visible_indices,
                y_price=y_price,
                body_width=body_width,
                price_bottom=price_bottom,
                max_volume=max_volume,
                volume_height=volume_height,
            )
        else:
            self._draw_candles(
                visible_indices,
                y_price=y_price,
                body_width=body_width,
                price_bottom=price_bottom,
                max_volume=max_volume,
                volume_height=volume_height,
            )

        def draw_line(values: list[float], color: str, width_px: int) -> None:
            points: list[float] = []
            for index in visible_indices:
                points.extend((self._x_from_index(index), y_price(values[index])))
            if len(points) >= 4:
                self.create_line(*points, fill=color, width=width_px)

        draw_line(self.ema_12, EMA_12_COLOR, 2)
        draw_line(self.ema_144, EMA_144_COLOR, 2)
        draw_line(self.ema_169, EMA_169_COLOR, 2)
        draw_line(self.ema_238, EMA_238_COLOR, 2)
        draw_line(self.ema_338, EMA_338_COLOR, 2)

        watermark_symbol = self.bundle.symbol.replace("/", "")
        self.create_text(
            (left + right) / 2,
            top + (price_bottom - top) * 0.52,
            text=f"{watermark_symbol}, {_format_interval_label(self.bundle.interval_minutes)}",
            fill="#9aa998",
            font=("Helvetica", 56),
        )

        for step in range(6):
            value = scale_top - (scale_range / 5) * step
            self.create_text(
                width - 12,
                y_price(value),
                text=f"{value:,.0f}",
                anchor="e",
                fill=TEXT_DIM,
                font=("Helvetica", 10),
            )

        current_close = float(self.bundle.candles[-1].close)
        y_current = y_price(current_close)
        self.create_line(left, y_current, right, y_current, fill="#9fb3aa", dash=(4, 4))
        self._draw_text_box(
            right + 6,
            y_current,
            _format_price(current_close),
            anchor="w",
            fill=PRICE_LABEL_FG,
            bg=PRICE_LABEL_BG,
            font=("Helvetica", 10, "bold"),
            pad_x=8,
            pad_y=4,
        )

        high_index = max(actual_visible, key=lambda index: float(self.bundle.candles[index].high))
        low_index = min(actual_visible, key=lambda index: float(self.bundle.candles[index].low))
        high_value = float(self.bundle.candles[high_index].high)
        low_value = float(self.bundle.candles[low_index].low)
        high_x = self._x_from_index(high_index)
        low_x = self._x_from_index(low_index)
        high_y = y_price(high_value)
        low_y = y_price(low_value)

        self.create_line(high_x, high_y - 2, high_x, high_y - 20, fill="#4d545c", arrow=tk.LAST)
        self._draw_text_box(
            high_x,
            high_y - 28,
            f"High  {_format_price(high_value)}",
            anchor="s",
            fill=TEXT,
            bg="#ffffff",
            outline="#d7dbde",
            font=("Helvetica", 10, "bold"),
            pad_x=8,
            pad_y=4,
        )

        self.create_line(low_x, low_y + 2, low_x, low_y + 20, fill="#4d545c", arrow=tk.LAST)
        self._draw_text_box(
            low_x,
            low_y + 28,
            f"Low  {_format_price(low_value)}",
            anchor="n",
            fill=TEXT,
            bg="#ffffff",
            outline="#d7dbde",
            font=("Helvetica", 10, "bold"),
            pad_x=8,
            pad_y=4,
        )

        if self.selected_indicators:
            self._draw_indicator_panes(
                visible_indices,
                left=left,
                right=right,
                indicator_top=indicator_top,
                bottom=bottom,
                body_width=body_width,
                width=width,
            )

        for step in range(6):
            relative = step / 5
            raw_index = self.view_left + relative * self.view_count
            label_index = max(0, min(len(self.bundle.candles) - 1, int(round(raw_index))))
            x = self._x_from_index(raw_index)
            label = self.bundle.candles[label_index].open_time.astimezone(UTC).strftime("%H:%M")
            self.create_text(x, bottom - 6, text=label, anchor="s", fill=TEXT, font=("Helvetica", 10))

        if self._hover_x is not None and self._hover_y is not None:
            self.create_line(self._hover_x, top, self._hover_x, bottom, fill="#6a737d", dash=(3, 4))
            self.create_line(left, self._hover_y, right, self._hover_y, fill="#6a737d", dash=(3, 4))

    def _clear_hover(self, *, notify: bool) -> None:
        previous_index = self._hover_index
        self._hover_index = None
        self._hover_x = None
        self._hover_y = None
        if notify and previous_index is not None:
            self._notify_hover(None)

    def _update_hover_state(self, x: float, y: float) -> None:
        if self.bundle is None:
            return
        if not self._plot_contains_point(x, y):
            self._clear_hover(notify=True)
            self._schedule_redraw()
            return

        index = self._index_from_x(x)
        position_changed = self._hover_x != x or self._hover_y != y
        index_changed = index != self._hover_index
        self._hover_x = x
        self._hover_y = y
        self._hover_index = index
        if index_changed:
            self._notify_hover(index)
        if position_changed or index_changed:
            self._schedule_redraw()

    def _on_press(self, event: tk.Event[tk.Misc]) -> None:
        if self.bundle is None:
            return
        if self._divider_hit(event.y):
            self._resizing_divider = True
            self._clear_hover(notify=True)
            self._schedule_redraw()
            return
        self._drag_start_x = event.x
        self._drag_start_view_left = self.view_left
        self._clear_hover(notify=True)
        self._schedule_redraw()

    def _on_drag(self, event: tk.Event[tk.Misc]) -> None:
        if self.bundle is None:
            return
        if self._resizing_divider:
            _, _, top, _, bottom, height = self._plot_geometry()
            min_height = 90.0
            max_height = max(min(height * 0.5, height - top - 80.0), min_height)
            self.indicator_area_height = max(min_height, min(max_height, bottom - event.y))
            self._schedule_redraw()
            return
        if self._drag_start_x is None or self._drag_start_view_left is None:
            return
        delta_pixels = event.x - self._drag_start_x
        self.view_left = self._clamp_view_left(self._drag_start_view_left - (delta_pixels / self._candle_space()))
        self._schedule_redraw()

    def _on_release(self, _event: tk.Event[tk.Misc]) -> None:
        self._resizing_divider = False
        self._drag_start_x = None
        self._drag_start_view_left = None

    def _on_motion(self, event: tk.Event[tk.Misc]) -> None:
        if self.bundle is None or self._drag_start_x is not None or self._resizing_divider:
            return
        self._update_hover_state(event.x, event.y)

    def _on_leave(self, _event: tk.Event[tk.Misc]) -> None:
        self._clear_hover(notify=False)
        if self.leave_callback is not None:
            self.leave_callback()
        self._schedule_redraw()

    def _zoom_at(self, x: float, factor: float) -> None:
        if self.bundle is None:
            return
        left, right, *_ = self._plot_geometry()
        if x < left or x > right:
            return
        relative = (x - left) / max(right - left, 1.0)
        anchor = self.view_left + relative * self.view_count
        new_count = max(24.0, min(float(len(self.bundle.candles)) + 40.0, self.view_count * factor))
        self.view_left = self._clamp_view_left(anchor - relative * new_count)
        self.view_count = new_count
        self._schedule_redraw()

    def _on_wheel(self, event: tk.Event[tk.Misc]) -> None:
        factor = ZOOM_IN_FACTOR if event.delta > 0 else ZOOM_OUT_FACTOR
        self._zoom_at(event.x, factor)
