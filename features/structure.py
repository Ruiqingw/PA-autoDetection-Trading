"""Explicit order block and fair value gap detection for chart overlays."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal

from config.settings import FeatureSettings
from data.models import Candle


@dataclass(slots=True)
class StructureZone:
    kind: str
    side: str
    start_time: str
    end_time: str
    lower_price: float
    upper_price: float
    label: str
    mitigated: bool

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _price_ratio(numerator: Decimal, denominator: Decimal) -> float:
    if denominator == 0:
        return 0.0
    return float(abs(numerator) / denominator)


def detect_fair_value_gaps(candles: list[Candle], settings: FeatureSettings) -> list[StructureZone]:
    zones: list[StructureZone] = []
    if len(candles) < 3:
        return zones

    for index in range(1, len(candles) - 1):
        previous_candle = candles[index - 1]
        impulse_candle = candles[index]
        next_candle = candles[index + 1]

        bullish_gap = next_candle.low - previous_candle.high
        if bullish_gap > 0 and _price_ratio(bullish_gap, impulse_candle.close) >= settings.fvg_min_gap_ratio:
            mitigated_index = next(
                (
                    mitigation_index
                    for mitigation_index in range(index + 2, len(candles))
                    if candles[mitigation_index].low <= previous_candle.high
                ),
                None,
            )
            if mitigated_index is None:
                zones.append(
                    StructureZone(
                        kind="fvg",
                        side="bullish",
                        start_time=impulse_candle.open_time.isoformat(),
                        end_time=candles[-1].close_time.isoformat(),
                        lower_price=float(previous_candle.high),
                        upper_price=float(next_candle.low),
                        label="FVG",
                        mitigated=False,
                    )
                )

        bearish_gap = previous_candle.low - next_candle.high
        if bearish_gap > 0 and _price_ratio(bearish_gap, impulse_candle.close) >= settings.fvg_min_gap_ratio:
            mitigated_index = next(
                (
                    mitigation_index
                    for mitigation_index in range(index + 2, len(candles))
                    if candles[mitigation_index].high >= previous_candle.low
                ),
                None,
            )
            if mitigated_index is None:
                zones.append(
                    StructureZone(
                        kind="fvg",
                        side="bearish",
                        start_time=impulse_candle.open_time.isoformat(),
                        end_time=candles[-1].close_time.isoformat(),
                        lower_price=float(next_candle.high),
                        upper_price=float(previous_candle.low),
                        label="FVG",
                        mitigated=False,
                    )
                )

    return zones[-settings.structure_zone_limit :]


def detect_order_blocks(candles: list[Candle], settings: FeatureSettings) -> list[StructureZone]:
    zones: list[StructureZone] = []
    if len(candles) < settings.ob_lookahead_candles + 2:
        return zones

    for index in range(1, len(candles) - settings.ob_lookahead_candles):
        candidate = candles[index]
        lookahead = candles[index + 1 : index + 1 + settings.ob_lookahead_candles]
        previous_window = candles[max(0, index - settings.ob_lookback_candles) : index + 1]
        previous_high = max(item.high for item in previous_window)
        previous_low = min(item.low for item in previous_window)

        bullish_displacement = max(item.high for item in lookahead) - candidate.close
        if (
            candidate.close < candidate.open
            and lookahead[0].close > candidate.high
            and max(item.close for item in lookahead) > previous_high
            and _price_ratio(bullish_displacement, candidate.close) >= settings.ob_displacement_ratio
        ):
            lower = float(candidate.low)
            upper = float(max(candidate.open, candidate.close))
            mitigated_index = next(
                (
                    mitigation_index
                    for mitigation_index in range(index + 1 + settings.ob_lookahead_candles, len(candles))
                    if candles[mitigation_index].low <= candidate.low
                ),
                len(candles) - 1,
            )
            zones.append(
                StructureZone(
                    kind="order_block",
                    side="bullish",
                    start_time=candidate.open_time.isoformat(),
                    end_time=candles[mitigated_index].close_time.isoformat(),
                    lower_price=lower,
                    upper_price=upper,
                    label="OB",
                    mitigated=mitigated_index != len(candles) - 1,
                )
            )

        bearish_displacement = candidate.close - min(item.low for item in lookahead)
        if (
            candidate.close > candidate.open
            and lookahead[0].close < candidate.low
            and min(item.close for item in lookahead) < previous_low
            and _price_ratio(bearish_displacement, candidate.close) >= settings.ob_displacement_ratio
        ):
            lower = float(min(candidate.open, candidate.close))
            upper = float(candidate.high)
            mitigated_index = next(
                (
                    mitigation_index
                    for mitigation_index in range(index + 1 + settings.ob_lookahead_candles, len(candles))
                    if candles[mitigation_index].high >= candidate.high
                ),
                len(candles) - 1,
            )
            zones.append(
                StructureZone(
                    kind="order_block",
                    side="bearish",
                    start_time=candidate.open_time.isoformat(),
                    end_time=candles[mitigated_index].close_time.isoformat(),
                    lower_price=lower,
                    upper_price=upper,
                    label="OB",
                    mitigated=mitigated_index != len(candles) - 1,
                )
            )

    return zones[-settings.structure_zone_limit :]


def detect_structure_zones(candles: list[Candle], settings: FeatureSettings) -> list[StructureZone]:
    zones = [
        *detect_order_blocks(candles, settings),
        *detect_fair_value_gaps(candles, settings),
    ]
    active_zones = [
        zone
        for zone in zones
        if zone.kind != "fvg" or not zone.mitigated
    ]
    return sorted(active_zones, key=lambda zone: zone.start_time)[-settings.structure_zone_limit :]
