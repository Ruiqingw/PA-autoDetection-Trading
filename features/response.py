"""Market-response metrics derived from flow and price movement."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal


@dataclass(slots=True)
class MarketResponseMetrics:
    price_return: float
    market_response: float
    blocked_buying_score: float
    blocked_selling_score: float

    def as_dict(self) -> dict[str, float]:
        return asdict(self)


def compute_price_return(start_price: Decimal, end_price: Decimal) -> float:
    if start_price <= 0:
        return 0.0
    return float((end_price - start_price) / start_price)


def compute_market_response(price_return: float, normalized_delta: float, *, min_flow: float = 0.05) -> float:
    """Measure how strongly price responded to trade flow.

    Formula:
    - market_response = price_return / max(abs(normalized_delta), min_flow)

    Interpretation:
    - positive values mean price moved with the dominant side
    - negative values mean price moved against the dominant side
    - larger magnitude means stronger price response per unit of flow
    """

    denominator = max(abs(normalized_delta), min_flow)
    return price_return / denominator if denominator > 0 else 0.0


def compute_blocked_buying_score(
    normalized_delta: float,
    price_return: float,
    *,
    response_scale_bps: float = 25.0,
) -> float:
    """Estimate absorbed buying.

    Formula:
    - expected_up_bps = max(normalized_delta, 0) * response_scale_bps
    - realized_up_bps = price_return * 10,000
    - blocked_buying_score = clamp((expected_up_bps - realized_up_bps) / response_scale_bps, 0, 1)

    Interpretation:
    - rises when buy flow is strong but price fails to rise proportionally
    - rises even more when buy flow is strong and price moves down instead
    """

    if normalized_delta <= 0:
        return 0.0
    expected_up_bps = normalized_delta * response_scale_bps
    realized_up_bps = price_return * 10_000
    return max(0.0, min((expected_up_bps - realized_up_bps) / response_scale_bps, 1.0))


def compute_blocked_selling_score(
    normalized_delta: float,
    price_return: float,
    *,
    response_scale_bps: float = 25.0,
) -> float:
    """Estimate absorbed selling.

    Formula:
    - expected_down_bps = max(-normalized_delta, 0) * response_scale_bps
    - realized_down_bps = -price_return * 10,000
    - blocked_selling_score = clamp((expected_down_bps - realized_down_bps) / response_scale_bps, 0, 1)

    Interpretation:
    - rises when sell flow is strong but price fails to fall proportionally
    - rises even more when sell flow is strong and price moves up instead
    """

    if normalized_delta >= 0:
        return 0.0
    expected_down_bps = abs(normalized_delta) * response_scale_bps
    realized_down_bps = -price_return * 10_000
    return max(0.0, min((expected_down_bps - realized_down_bps) / response_scale_bps, 1.0))


def compute_response_metrics(
    start_price: Decimal,
    end_price: Decimal,
    normalized_delta: float,
    *,
    min_flow: float = 0.05,
    response_scale_bps: float = 25.0,
) -> MarketResponseMetrics:
    price_return = compute_price_return(start_price, end_price)
    return MarketResponseMetrics(
        price_return=price_return,
        market_response=compute_market_response(price_return, normalized_delta, min_flow=min_flow),
        blocked_buying_score=compute_blocked_buying_score(
            normalized_delta,
            price_return,
            response_scale_bps=response_scale_bps,
        ),
        blocked_selling_score=compute_blocked_selling_score(
            normalized_delta,
            price_return,
            response_scale_bps=response_scale_bps,
        ),
    )
