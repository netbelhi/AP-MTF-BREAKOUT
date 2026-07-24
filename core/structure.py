# -*- coding: utf-8 -*-
"""
Structure layer — swing pivots, Fair Value Gaps, Order Blocks, and BOS/CHoCH
trend events. Used to (a) determine the HTF trend for MTF confluence and
(b) tag breakout/false-breakout signals with SMC confirmation (unmitigated
Order Block or FVG near the entry, matching direction).
"""

from dataclasses import dataclass, field
from typing import List, Optional
import numpy as np
import pandas as pd


@dataclass
class Pivot:
    pos: int
    timestamp: object
    price: float
    kind: str   # 'H' | 'L'


@dataclass
class FVGZone:
    kind: str          # 'bullish' | 'bearish'
    top: float
    bottom: float
    pos: int
    timestamp: object


@dataclass
class OrderBlock:
    kind: str
    top: float
    bottom: float
    pos: int
    timestamp: object
    mitigated: bool = False


@dataclass
class StructureEvent:
    kind: str           # 'BOS' | 'CHoCH'
    direction: str        # 'bullish' | 'bearish'
    pos: int
    price: float
    timestamp: object


@dataclass
class ConfluenceResult:
    score: int
    tags: List[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        if self.score >= 2:
            return "🟢🟢 Strong MTF Confluence"
        if self.score == 1:
            return "🟡 Partial Confluence"
        return "—"


# ---------------------------------------------------------------------------
# Swing pivots
# ---------------------------------------------------------------------------
def find_price_pivots(close: pd.Series, left: int, right: int) -> List[Pivot]:
    vals = close.values
    n = len(vals)
    pivots: List[Pivot] = []
    for i in range(left, n - right):
        window = vals[i - left: i + right + 1]
        v = vals[i]
        if np.isnan(v) or np.isnan(window).any():
            continue
        center = left
        if v == window.max() and np.argmax(window) == center:
            pivots.append(Pivot(i, close.index[i], float(v), "H"))
        elif v == window.min() and np.argmin(window) == center:
            pivots.append(Pivot(i, close.index[i], float(v), "L"))
    return pivots


# ---------------------------------------------------------------------------
# Fair Value Gaps + Order Blocks
# ---------------------------------------------------------------------------
def find_fvgs(df: pd.DataFrame) -> List[FVGZone]:
    h = df["High"].values
    l = df["Low"].values
    n = len(df)
    zones: List[FVGZone] = []
    for i in range(1, n - 1):
        if l[i + 1] > h[i - 1]:
            zones.append(FVGZone("bullish", top=float(l[i + 1]), bottom=float(h[i - 1]),
                                  pos=i, timestamp=df.index[i]))
        elif h[i + 1] < l[i - 1]:
            zones.append(FVGZone("bearish", top=float(l[i - 1]), bottom=float(h[i + 1]),
                                  pos=i, timestamp=df.index[i]))
    return zones


def find_order_blocks(df: pd.DataFrame, fvgs: List[FVGZone]) -> List[OrderBlock]:
    o = df["Open"].values
    c = df["Close"].values
    obs: List[OrderBlock] = []
    for fvg in fvgs:
        ob_pos = fvg.pos - 1
        if ob_pos < 0:
            continue
        body_top = float(max(o[ob_pos], c[ob_pos]))
        body_bottom = float(min(o[ob_pos], c[ob_pos]))
        if fvg.kind == "bullish" and c[ob_pos] < o[ob_pos]:
            obs.append(OrderBlock("bullish", top=body_top, bottom=body_bottom,
                                   pos=ob_pos, timestamp=df.index[ob_pos]))
        elif fvg.kind == "bearish" and c[ob_pos] > o[ob_pos]:
            obs.append(OrderBlock("bearish", top=body_top, bottom=body_bottom,
                                   pos=ob_pos, timestamp=df.index[ob_pos]))

    close = df["Close"].values
    for ob in obs:
        after = close[ob.pos + 1:]
        if len(after) == 0:
            continue
        ob.mitigated = bool(np.any(after < ob.bottom)) if ob.kind == "bullish" else bool(np.any(after > ob.top))
    return obs


# ---------------------------------------------------------------------------
# BOS / CHoCH structure events (pivot-level swing-break state machine)
# ---------------------------------------------------------------------------
def detect_structure_events(pivots: List[Pivot]) -> List[StructureEvent]:
    events: List[StructureEvent] = []
    ordered = sorted(pivots, key=lambda p: p.pos)

    last_high: Optional[Pivot] = None
    last_low: Optional[Pivot] = None
    trend = None

    for p in ordered:
        if p.kind == "H":
            if last_high is not None and p.price > last_high.price:
                kind = "BOS" if trend == "up" else "CHoCH"
                events.append(StructureEvent(kind, "bullish", p.pos, p.price, p.timestamp))
                trend = "up"
            last_high = p
        else:
            if last_low is not None and p.price < last_low.price:
                kind = "BOS" if trend == "down" else "CHoCH"
                events.append(StructureEvent(kind, "bearish", p.pos, p.price, p.timestamp))
                trend = "down"
            last_low = p

    return events


def current_trend(structure_events: List[StructureEvent]) -> Optional[str]:
    """Direction of the most recent structure event — used as the HTF trend read."""
    if not structure_events:
        return None
    return max(structure_events, key=lambda e: e.pos).direction


# ---------------------------------------------------------------------------
# Confluence scoring for a breakout/false-breakout signal
# ---------------------------------------------------------------------------
def compute_confluence(
    direction: str,
    entry_price: float,
    entry_pos: int,
    fvgs: List[FVGZone],
    obs: List[OrderBlock],
    htf_trend: Optional[str],
    lookback_bars: int,
    zone_tolerance: float,
) -> ConfluenceResult:
    tags: List[str] = []
    score = 0

    if htf_trend is not None and htf_trend == direction:
        tags.append(f"HTF trend aligned ({htf_trend.title()})")
        score += 1

    candidate_obs = [
        ob for ob in obs
        if ob.kind == direction and not ob.mitigated
        and ob.pos <= entry_pos and (entry_pos - ob.pos) <= lookback_bars
    ]
    for ob in sorted(candidate_obs, key=lambda o: -o.pos):
        lo, hi = ob.bottom * (1 - zone_tolerance), ob.top * (1 + zone_tolerance)
        if lo <= entry_price <= hi:
            tags.append(f"{direction.title()} Order Block @ {ob.bottom:.1f}-{ob.top:.1f}")
            score += 1
            break

    candidate_fvgs = [
        f for f in fvgs
        if f.kind == direction and f.pos <= entry_pos and (entry_pos - f.pos) <= lookback_bars
    ]
    for f in sorted(candidate_fvgs, key=lambda x: -x.pos):
        lo, hi = f.bottom * (1 - zone_tolerance), f.top * (1 + zone_tolerance)
        if lo <= entry_price <= hi:
            tags.append(f"{direction.title()} FVG @ {f.bottom:.1f}-{f.top:.1f}")
            score += 1
            break

    return ConfluenceResult(score=score, tags=tags)
