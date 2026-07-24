# -*- coding: utf-8 -*-
"""
Advanced price-action layer — candlestick pattern recognition, wick-rejection
/ continuation strength, and ATR-based momentum ("Sign of Strength / Sign of
Weakness"). Used to add a Price-Action confidence score on top of each
breakout/false-breakout signal, independent of the MTF/SMC confluence score.
"""

from dataclasses import dataclass, field
from typing import List, Optional
import pandas as pd


@dataclass
class CandlePattern:
    pos: int
    timestamp: object
    pattern: str
    bias: str   # 'bullish' | 'bearish' | 'neutral'


@dataclass
class PriceActionScore:
    score: int
    tags: List[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        if self.score >= 2:
            return "🔥 Strong Price Action"
        if self.score == 1:
            return "🟡 Some Price Action"
        return "—"


def classify_candle(o, h, l, c, prev=None) -> Optional[str]:
    """Pattern for one candle; `prev` = (open, high, low, close) of the previous
    candle, needed for Engulfing / Inside Bar."""
    rng = h - l
    if rng <= 0:
        return None
    body = abs(c - o)
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l
    body_pct = body / rng

    pattern = None
    if body_pct < 0.12:
        pattern = "Doji"
    elif lower_wick >= 2 * body and lower_wick / rng > 0.55:
        pattern = "Bullish Pin Bar"
    elif upper_wick >= 2 * body and upper_wick / rng > 0.55:
        pattern = "Bearish Pin Bar"

    if prev is not None:
        po, ph, pl, pc = prev
        p_top, p_bottom = max(po, pc), min(po, pc)
        top, bottom = max(o, c), min(o, c)
        if c > o and pc < po and top >= p_top and bottom <= p_bottom:
            pattern = "Bullish Engulfing"
        elif c < o and pc > po and top >= p_top and bottom <= p_bottom:
            pattern = "Bearish Engulfing"
        elif h <= ph and l >= pl:
            pattern = pattern or "Inside Bar"

    return pattern


def detect_patterns(df: pd.DataFrame) -> List[CandlePattern]:
    o, h, l, c = df["Open"].values, df["High"].values, df["Low"].values, df["Close"].values
    bias_map = {
        "Doji": "neutral", "Inside Bar": "neutral",
        "Bullish Pin Bar": "bullish", "Bearish Pin Bar": "bearish",
        "Bullish Engulfing": "bullish", "Bearish Engulfing": "bearish",
    }
    out: List[CandlePattern] = []
    for i in range(len(df)):
        prev = (o[i - 1], h[i - 1], l[i - 1], c[i - 1]) if i > 0 else None
        pat = classify_candle(o[i], h[i], l[i], c[i], prev)
        if pat:
            out.append(CandlePattern(i, df.index[i], pat, bias_map.get(pat, "neutral")))
    return out


def rejection_strength(o: float, h: float, l: float, c: float, direction: str) -> float:
    """0-1: how much of the candle's range is a rejecting wick.
    direction='bearish' -> upper-wick ratio (rejecting a high). 'bullish' -> lower-wick ratio."""
    rng = h - l
    if rng <= 0:
        return 0.0
    if direction == "bearish":
        return float((h - max(o, c)) / rng)
    return float((min(o, c) - l) / rng)


def continuation_strength(o: float, h: float, l: float, c: float, direction: str) -> float:
    """0-1: how close the candle closed to its extreme in the move's direction
    (no wick fighting the move) — used for Confirmed breakouts."""
    rng = h - l
    if rng <= 0:
        return 0.0
    if direction == "bullish":
        return float((c - l) / rng)
    return float((h - c) / rng)


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    h, l, c = df["High"], df["Low"], df["Close"]
    prev_c = c.shift(1)
    tr = pd.concat([h - l, (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def is_momentum_candle(df: pd.DataFrame, atr: pd.Series, pos: int, multiple: float = 1.15) -> bool:
    if pos < 0 or pos >= len(df) or pd.isna(atr.iloc[pos]) or atr.iloc[pos] <= 0:
        return False
    rng = df["High"].iloc[pos] - df["Low"].iloc[pos]
    return bool(rng >= multiple * atr.iloc[pos])


def compute_price_action_score(
    direction: str,
    decision_pos: int,
    patterns: List[CandlePattern],
    df: pd.DataFrame,
    atr: pd.Series,
    strength_ratio: Optional[float] = None,
    strength_threshold: float = 0.5,
    momentum_multiple: float = 1.15,
) -> PriceActionScore:
    tags: List[str] = []
    score = 0

    matching = [p for p in patterns if p.pos == decision_pos and p.bias == direction]
    if matching:
        tags.append(f"{matching[0].pattern} candle")
        score += 1

    if strength_ratio is not None and strength_ratio >= strength_threshold:
        tags.append(f"Strong wick/close ratio ({strength_ratio * 100:.0f}%)")
        score += 1

    if is_momentum_candle(df, atr, decision_pos, momentum_multiple):
        tags.append("Momentum candle (range > ATR) — Sign of Strength")
        score += 1

    return PriceActionScore(score=score, tags=tags)
