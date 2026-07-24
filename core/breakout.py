# -*- coding: utf-8 -*-
"""
Core breakout / false-breakout (liquidity-sweep) detection.

For every level (ORB/PDH/PDL/PWH/PWL/Swing), walk forward from the bar the
level became live and find the FIRST bar that tests it:
  - Wick pierces the level but the candle CLOSES back on the original side
    -> immediate 'False' breakout (classic liquidity sweep / stop-hunt).
  - Candle CLOSES beyond the level -> tentatively a breakout; check the next
    `confirm_bars` candles:
      - all still close beyond  -> 'Confirmed' breakout (trade WITH direction)
      - closes back across the level -> 'False' (breakout trap, trade AGAINST
        the initial break direction)
      - not enough future bars yet -> 'Pending'
"""

from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import pandas as pd

from core.levels import Level, _is_high_kind


@dataclass
class BreakoutEvent:
    level: Level
    direction: str        # 'bullish' | 'bearish' — the direction to actually TRADE
    status: str             # 'Confirmed' | 'False' | 'Pending'
    test_pos: int
    confirm_pos: int
    test_price: float          # extreme (wick) price reached during the test
    close_price: float           # close of the confirmation/rejection bar
    timestamp: object
    signal_key: str


@dataclass
class TradePlan:
    entry: float
    stop_loss: float
    target1: float
    target2: float
    risk_points: float
    rr1: float
    rr2: float
    basis: str


def detect_breakouts(
    df: pd.DataFrame,
    levels: List[Level],
    symbol: str,
    timeframe: str,
    confirm_bars: int = 1,
) -> List[BreakoutEvent]:
    events: List[BreakoutEvent] = []
    high = df["High"].values
    low = df["Low"].values
    close = df["Close"].values
    n = len(df)

    for lvl in levels:
        is_high = _is_high_kind(lvl.kind)
        start = lvl.formed_pos + 1
        if start >= n:
            continue

        for i in range(start, n):
            touched = (high[i] > lvl.price) if is_high else (low[i] < lvl.price)
            if not touched:
                continue

            test_pos = i
            test_price = float(high[i]) if is_high else float(low[i])
            closed_beyond = (close[i] > lvl.price) if is_high else (close[i] < lvl.price)

            if not closed_beyond:
                direction = "bearish" if is_high else "bullish"
                events.append(BreakoutEvent(
                    lvl, direction, "False", test_pos, test_pos, test_price, float(close[i]),
                    df.index[test_pos],
                    f"{symbol}|{timeframe}|{lvl.kind}|{lvl.label}|{test_pos}|False",
                ))
                break

            confirm_end = i + confirm_bars
            if confirm_end >= n:
                direction = "bullish" if is_high else "bearish"
                events.append(BreakoutEvent(
                    lvl, direction, "Pending", test_pos, i, test_price, float(close[i]),
                    df.index[i],
                    f"{symbol}|{timeframe}|{lvl.kind}|{lvl.label}|{test_pos}|Pending",
                ))
                break

            still_beyond = all(
                (close[j] > lvl.price) if is_high else (close[j] < lvl.price)
                for j in range(i, confirm_end + 1)
            )
            if still_beyond:
                status = "Confirmed"
                direction = "bullish" if is_high else "bearish"
            else:
                status = "False"
                direction = "bearish" if is_high else "bullish"

            events.append(BreakoutEvent(
                lvl, direction, status, test_pos, confirm_end, test_price, float(close[confirm_end]),
                df.index[confirm_end],
                f"{symbol}|{timeframe}|{lvl.kind}|{lvl.label}|{test_pos}|{status}",
            ))
            break

    return events


def compute_trade_plan(
    event: BreakoutEvent,
    buffer_pct: float = 0.0015,
    rr1: float = 1.5,
    rr2: float = 3.0,
) -> Optional[TradePlan]:
    if event.status not in ("Confirmed", "Pending", "False"):
        return None

    lvl_price = event.level.price
    entry = event.close_price

    if event.status == "Confirmed":
        # trade WITH the breakout
        if event.direction == "bullish":
            sl = lvl_price * (1 - buffer_pct)
            if sl >= entry:
                sl = entry * (1 - buffer_pct * 3)
            risk = entry - sl
            t1, t2 = entry + rr1 * risk, entry + rr2 * risk
        else:
            sl = lvl_price * (1 + buffer_pct)
            if sl <= entry:
                sl = entry * (1 + buffer_pct * 3)
            risk = sl - entry
            t1, t2 = entry - rr1 * risk, entry - rr2 * risk
        basis = f"{event.level.kind} Confirmed Breakout"

    else:
        # False breakout (or a Pending one, previewed as if it fails) -> fade the sweep
        if event.direction == "bullish":
            sl = event.test_price * (1 - buffer_pct)
            risk = entry - sl
            if risk <= 0:
                risk = entry * 0.005
                sl = entry - risk
            t1, t2 = entry + rr1 * risk, entry + rr2 * risk
        else:
            sl = event.test_price * (1 + buffer_pct)
            risk = sl - entry
            if risk <= 0:
                risk = entry * 0.005
                sl = entry + risk
            t1, t2 = entry - rr1 * risk, entry - rr2 * risk
        tag = "False Breakout (Liquidity Sweep)" if event.status == "False" else "Pending — preview if it fails"
        basis = f"{event.level.kind} {tag}"

    return TradePlan(entry=entry, stop_loss=sl, target1=t1, target2=t2,
                      risk_points=risk, rr1=rr1, rr2=rr2, basis=basis)


def latest_per_level_kind(events: List[BreakoutEvent], keep_n: int = 8) -> List[BreakoutEvent]:
    """Keep only the most recent events (across all levels), most-recent first."""
    return sorted(events, key=lambda e: e.confirm_pos, reverse=True)[:keep_n]
