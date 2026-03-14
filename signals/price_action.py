"""Explicit bearish price-action setup detection."""

from __future__ import annotations

from decimal import Decimal

from config.settings import BearishSetupSettings
from data.models import Candle, SignalRecord


def _range(candles: list[Candle]) -> Decimal:
    return max(c.high for c in candles) - min(c.low for c in candles)


def detect_bearish_breakdown_retest(
    candles: list[Candle],
    *,
    timeframe: str,
    settings: BearishSetupSettings,
    bearish_flow_score: float = 0.0,
    blocked_buying_score: float = 0.0,
    book_imbalance: float = 0.0,
) -> SignalRecord | None:
    """Detect a simple bearish structure.

    Rules:
    1. Impulsive selloff:
       - use `selloff_lookback_candles`
       - require return <= `min_selloff_return`
    2. Contraction:
       - use `consolidation_candles`
       - require consolidation range <= selloff range * `max_consolidation_range_ratio`
    3. Downside break:
       - breakdown close must be below consolidation support by `breakdown_close_buffer`
    4. Retest failure:
       - retest high must revisit support within `retest_tolerance`
       - retest close must finish back below support and below its open
    """

    pattern_length = settings.selloff_lookback_candles + settings.consolidation_candles + 2
    if len(candles) < pattern_length:
        return None

    best_signal: SignalRecord | None = None
    for end_index in range(pattern_length, len(candles) + 1):
        window = candles[end_index - pattern_length : end_index]
        impulse = window[: settings.selloff_lookback_candles]
        consolidation = window[
            settings.selloff_lookback_candles : settings.selloff_lookback_candles + settings.consolidation_candles
        ]
        breakdown = window[-2]
        retest = window[-1]

        selloff_return = float((impulse[-1].close - impulse[0].open) / impulse[0].open)
        if selloff_return > settings.min_selloff_return:
            continue

        impulse_range = _range(impulse)
        consolidation_range = _range(consolidation)
        if impulse_range <= 0:
            continue
        if consolidation_range > impulse_range * Decimal(str(settings.max_consolidation_range_ratio)):
            continue

        support_level = min(c.low for c in consolidation)
        breakdown_limit = support_level * Decimal(str(1 - settings.breakdown_close_buffer))
        if breakdown.close >= breakdown_limit:
            continue

        retest_floor = support_level * Decimal(str(1 - settings.retest_tolerance))
        retest_ceiling = support_level * Decimal(str(1 + settings.retest_tolerance))
        revisited_support = retest.high >= retest_floor and retest.low <= retest_ceiling
        rejected_reclaim = (
            retest.close < support_level * Decimal(str(1 - settings.retest_rejection_close_buffer))
            and retest.close < retest.open
        )
        if not revisited_support or not rejected_reclaim:
            continue

        flow_confirmation = max(0.0, bearish_flow_score)
        absorption_confirmation = max(0.0, blocked_buying_score)
        imbalance_confirmation = max(0.0, -book_imbalance)
        confidence = min(
            1.0,
            0.35
            + min(abs(selloff_return) / abs(settings.min_selloff_return), 1.0) * 0.25
            + min(flow_confirmation, 1.0) * 0.15
            + min(absorption_confirmation, 1.0) * 0.15
            + min(imbalance_confirmation, 1.0) * 0.10,
        )

        signal = SignalRecord(
            symbol=retest.symbol,
            timeframe=timeframe,
            setup_name="bearish_breakdown_retest",
            detected_at=retest.close_time,
            support_level=support_level,
            entry_trigger=min(breakdown.low, retest.low),
            invalidation_level=max(max(c.high for c in consolidation), retest.high),
            confidence_score=confidence,
            notes=(
                "Impulsive selloff into contraction, downside break, and failed retest below support."
            ),
            metadata={
                "selloff_return": selloff_return,
                "consolidation_range": str(consolidation_range),
                "impulse_range": str(impulse_range),
                "bearish_flow_score": bearish_flow_score,
                "blocked_buying_score": blocked_buying_score,
                "book_imbalance": book_imbalance,
            },
        )
        best_signal = signal
    return best_signal
