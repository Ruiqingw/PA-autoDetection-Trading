"""TradingView-inspired chart helpers for the desktop dashboard."""

from __future__ import annotations

from dataclasses import dataclass

from matplotlib.axes import Axes
from matplotlib import dates as mdates
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
from matplotlib.text import Annotation

from data.models import Candle
from services.monitor import MonitorBundle


PRICE_UP = "#22ab94"
PRICE_DOWN = "#f23645"
EMA_12_COLOR = "#ff9800"
EMA_144_COLOR = "#2962ff"
EMA_169_COLOR = "#ff5a36"
EMA_238_COLOR = "#f2c94c"
EMA_338_COLOR = "#4caf50"
EMA_PERIODS = (12, 144, 169, 238, 338)
OSC_FAST = "#6f63ff"
OSC_SLOW = "#ffcb2f"
TEXT_COLOR = "#20242a"
MUTED_COLOR = "#66717d"
PRICE_LABEL_BG = "#1faa8f"
PRICE_LABEL_TEXT = "#ffffff"
PRICE_BG = "#d3e9cf"
OSC_BG = "#cfe6c9"
FIGURE_BG = "#d7ead3"
VOLUME_UP = (34 / 255, 171 / 255, 148 / 255, 0.18)
VOLUME_DOWN = (242 / 255, 54 / 255, 69 / 255, 0.18)
MARKER_COLOR = "#2b2f35"


@dataclass(slots=True)
class ChartSummary:
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    ema_12: float
    ema_144: float
    ema_169: float
    ema_238: float
    ema_338: float
    price_change: float
    percent_change: float


@dataclass(slots=True)
class ChartView:
    figure: Figure
    price_ax: Axes
    flow_ax: Axes
    candles: list[Candle]
    x_values: list[float]
    highs: list[float]
    lows: list[float]
    initial_xlim: tuple[float, float]
    candle_span: float
    high_annotation: Annotation
    low_annotation: Annotation


def _format_price(value: float) -> str:
    return f"{value:,.2f}"


def _ema(values: list[float], span: int) -> list[float]:
    if not values:
        return []
    alpha = 2 / (span + 1)
    ema_values = [values[0]]
    for value in values[1:]:
        ema_values.append((alpha * value) + ((1 - alpha) * ema_values[-1]))
    return ema_values


def summarize_market_chart(bundle: MonitorBundle, candle_index: int | None = None) -> ChartSummary:
    closes = [float(candle.close) for candle in bundle.candles]
    opens = [float(candle.open) for candle in bundle.candles]
    highs = [float(candle.high) for candle in bundle.candles]
    lows = [float(candle.low) for candle in bundle.candles]
    ema_12 = _ema(closes, 12)
    ema_144 = _ema(closes, 144)
    ema_169 = _ema(closes, 169)
    ema_238 = _ema(closes, 238)
    ema_338 = _ema(closes, 338)
    selected_index = candle_index if candle_index is not None else len(closes) - 1
    previous_close = closes[selected_index - 1] if selected_index > 0 else closes[selected_index]
    price_change = closes[selected_index] - previous_close
    percent_change = (price_change / previous_close * 100) if previous_close else 0.0
    return ChartSummary(
        open_price=opens[selected_index],
        high_price=highs[selected_index],
        low_price=lows[selected_index],
        close_price=closes[selected_index],
        ema_12=ema_12[selected_index],
        ema_144=ema_144[selected_index],
        ema_169=ema_169[selected_index],
        ema_238=ema_238[selected_index],
        ema_338=ema_338[selected_index],
        price_change=price_change,
        percent_change=percent_change,
    )


def _visible_indices(chart_view: ChartView) -> list[int]:
    left, right = chart_view.price_ax.get_xlim()
    return [
        index
        for index, x_value in enumerate(chart_view.x_values)
        if left <= x_value <= right
    ]


def update_visible_extrema(chart_view: ChartView) -> None:
    visible = _visible_indices(chart_view)
    if not visible:
        return

    visible_high_index = max(visible, key=lambda index: chart_view.highs[index])
    visible_low_index = min(visible, key=lambda index: chart_view.lows[index])
    visible_high = chart_view.highs[visible_high_index]
    visible_low = chart_view.lows[visible_low_index]

    chart_view.high_annotation.xy = (chart_view.x_values[visible_high_index], visible_high)
    chart_view.high_annotation.set_text(f"High  {_format_price(visible_high)}")
    chart_view.low_annotation.xy = (chart_view.x_values[visible_low_index], visible_low)
    chart_view.low_annotation.set_text(f"Low  {_format_price(visible_low)}")


def build_market_figure(
    bundle: MonitorBundle,
    *,
    max_points: int = 84,
    show_blocked_indicators: bool = True,
) -> ChartView:
    candles = bundle.candles
    series = bundle.candle_feature_series
    closes = [float(candle.close) for candle in bundle.candles]
    ema_12 = _ema(closes, 12)[-len(candles):]
    ema_144 = _ema(closes, 144)[-len(candles):]
    ema_169 = _ema(closes, 169)[-len(candles):]
    ema_238 = _ema(closes, 238)[-len(candles):]
    ema_338 = _ema(closes, 338)[-len(candles):]

    x_values = [mdates.date2num(candle.open_time) for candle in candles]
    highs = [float(candle.high) for candle in candles]
    lows = [float(candle.low) for candle in candles]
    opens = [float(candle.open) for candle in candles]
    last_close = float(candles[-1].close)
    min_price = min(lows)
    max_price = max(highs)
    price_range = max(max_price - min_price, 1.0)
    volume_scale = price_range * 0.17
    max_volume = max(float(candle.volume) for candle in candles)

    if len(x_values) > 1:
        candle_width = (x_values[1] - x_values[0]) * 0.58
        candle_span = x_values[1] - x_values[0]
    else:
        candle_width = 0.02
        candle_span = 0.02

    figure = Figure(figsize=(12.5, 8.6), facecolor=FIGURE_BG)
    grid = figure.add_gridspec(2, 1, height_ratios=[4.2, 1.45], hspace=0.0)
    price_ax = figure.add_subplot(grid[0])
    flow_ax = figure.add_subplot(grid[1], sharex=price_ax)

    price_ax.set_facecolor(PRICE_BG)
    flow_ax.set_facecolor(OSC_BG)

    for axis in (price_ax, flow_ax):
        for side in ("top", "left", "bottom", "right"):
            axis.spines[side].set_visible(False)
        axis.tick_params(axis="both", colors=MUTED_COLOR, length=0, labelsize=9)
        axis.yaxis.tick_right()
        axis.grid(False)

    price_ax.tick_params(axis="x", labelbottom=False)
    flow_ax.tick_params(axis="x", colors=TEXT_COLOR)

    for x_value, candle, open_price, high_price, low_price in zip(
        x_values,
        candles,
        opens,
        highs,
        lows,
        strict=True,
    ):
        close_price = float(candle.close)
        color = PRICE_UP if close_price >= open_price else PRICE_DOWN
        price_ax.vlines(x_value, low_price, high_price, color=color, linewidth=1.1, zorder=3)
        body_bottom = min(open_price, close_price)
        body_height = max(abs(close_price - open_price), max(price_range * 0.0012, 0.8))
        price_ax.add_patch(
            Rectangle(
                (x_value - candle_width / 2, body_bottom),
                candle_width,
                body_height,
                facecolor=color,
                edgecolor=color,
                linewidth=0.0,
                zorder=4,
            )
        )
        volume_height = (float(candle.volume) / max_volume) * volume_scale
        volume_bottom = min_price
        price_ax.add_patch(
            Rectangle(
                (x_value - candle_width / 2, volume_bottom),
                candle_width,
                volume_height,
                facecolor=VOLUME_UP if close_price >= open_price else VOLUME_DOWN,
                edgecolor="none",
                zorder=1,
            )
        )

    price_ax.plot(x_values, ema_12, color=EMA_12_COLOR, linewidth=1.3, zorder=5)
    price_ax.plot(x_values, ema_144, color=EMA_144_COLOR, linewidth=1.3, zorder=5)
    price_ax.plot(x_values, ema_169, color=EMA_169_COLOR, linewidth=1.15, zorder=5)
    price_ax.plot(x_values, ema_238, color=EMA_238_COLOR, linewidth=1.15, zorder=5)
    price_ax.plot(x_values, ema_338, color=EMA_338_COLOR, linewidth=1.1, zorder=5)

    price_ax.axhline(last_close, color=(17 / 255, 19 / 255, 22 / 255, 0.18), linestyle="--", linewidth=0.9, zorder=2)
    if bundle.analysis.signal is not None:
        support_level = float(bundle.analysis.signal.support_level)
        price_ax.axhline(
            support_level,
            color=(17 / 255, 19 / 255, 22 / 255, 0.22),
            linewidth=0.9,
            zorder=2,
        )

    high_index = highs.index(max_price)
    low_index = lows.index(min_price)
    high_annotation = price_ax.annotate(
        f"High  {_format_price(max_price)}",
        xy=(x_values[high_index], max_price),
        xytext=(0, -28),
        textcoords="offset points",
        ha="center",
        va="bottom",
        fontsize=8.5,
        color=MARKER_COLOR,
        bbox={"boxstyle": "round,pad=0.35", "fc": (1, 1, 1, 0.92), "ec": (0, 0, 0, 0.08)},
        arrowprops={"arrowstyle": "-|>", "color": (0, 0, 0, 0.45), "lw": 0.8},
        zorder=7,
    )
    low_annotation = price_ax.annotate(
        f"Low  {_format_price(min_price)}",
        xy=(x_values[low_index], min_price),
        xytext=(0, 28),
        textcoords="offset points",
        ha="center",
        va="top",
        fontsize=8.5,
        color=MARKER_COLOR,
        bbox={"boxstyle": "round,pad=0.35", "fc": (1, 1, 1, 0.92), "ec": (0, 0, 0, 0.08)},
        arrowprops={"arrowstyle": "-|>", "color": (0, 0, 0, 0.45), "lw": 0.8},
        zorder=7,
        annotation_clip=False,
    )

    if show_blocked_indicators:
        markers = [marker for marker in bundle.imbalance_markers if marker.timestamp >= candles[0].open_time][-6:]
        for marker in markers:
            x_marker = mdates.date2num(marker.timestamp)
            marker_y = float(marker.price)
            blocked_buy = marker.label == "Blocked buying"
            price_ax.scatter(
                [x_marker],
                [marker_y],
                color="#2c3e50" if blocked_buy else "#8c1c13",
                marker="v" if blocked_buy else "^",
                s=22,
                zorder=6,
            )

    watermark_symbol = bundle.symbol.replace("/", "")
    price_ax.text(
        x_values[len(x_values) // 2],
        min_price + price_range * 0.44,
        f"{watermark_symbol}, {bundle.interval_minutes}m" if bundle.interval_minutes < 60 else f"{watermark_symbol}, {bundle.interval_minutes // 60}h",
        color=(17 / 255, 19 / 255, 22 / 255, 0.10),
        fontsize=44,
        ha="center",
        va="center",
        zorder=0,
    )

    buy_strength = [point.buy_strength * 100 for point in series]
    sell_strength = [point.sell_strength * 100 for point in series]
    flow_ax.plot(x_values, buy_strength, color=OSC_FAST, linewidth=1.35)
    flow_ax.plot(x_values, sell_strength, color=OSC_SLOW, linewidth=1.15)
    for level in (30, 50, 70):
        flow_ax.axhline(level, color=(17 / 255, 19 / 255, 22 / 255, 0.16), linestyle=(0, (4, 6)), linewidth=0.8)
    flow_ax.set_ylim(0, 100)
    flow_ax.set_yticks([20, 40, 60, 80])
    flow_ax.text(
        x_values[0],
        96,
        "Flow strength",
        color=MUTED_COLOR,
        fontsize=9.5,
        va="top",
    )

    locator = mdates.AutoDateLocator(minticks=6, maxticks=8)
    formatter = mdates.ConciseDateFormatter(locator)
    flow_ax.xaxis.set_major_locator(locator)
    flow_ax.xaxis.set_major_formatter(formatter)

    price_ax.annotate(
        _format_price(last_close),
        xy=(1, last_close),
        xycoords=("axes fraction", "data"),
        xytext=(8, 0),
        textcoords="offset points",
        ha="left",
        va="center",
        fontsize=9,
        color=PRICE_LABEL_TEXT,
        bbox={"boxstyle": "round,pad=0.25", "fc": PRICE_LABEL_BG, "ec": "none"},
        zorder=8,
    )

    y_padding = price_range * 0.12
    price_ax.set_ylim(min_price - y_padding * 0.62, max_price + y_padding * 0.14)
    initial_points = min(max_points, len(x_values))
    visible_width = candle_span * max(initial_points - 1, 1)
    right_offset = max(visible_width * 0.12, candle_span * 6)
    initial_right = x_values[-1] + right_offset
    initial_left = initial_right - visible_width
    price_ax.set_xlim(initial_left, initial_right)
    figure.subplots_adjust(left=0.02, right=0.95, top=0.98, bottom=0.08)
    chart_view = ChartView(
        figure=figure,
        price_ax=price_ax,
        flow_ax=flow_ax,
        candles=candles,
        x_values=x_values,
        highs=highs,
        lows=lows,
        initial_xlim=(initial_left, initial_right),
        candle_span=candle_span,
        high_annotation=high_annotation,
        low_annotation=low_annotation,
    )
    update_visible_extrema(chart_view)
    return chart_view
