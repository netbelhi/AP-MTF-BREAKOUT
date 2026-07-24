# -*- coding: utf-8 -*-
"""
Builds the price "levels" that breakouts/false-breakouts get tested against:
  - Opening Range High/Low (ORB) — first N minutes of each trading day
  - Previous Day High/Low (PDH/PDL)
  - Previous Week High/Low (PWH/PWL)
  - Recent swing structure High/Low (from pivot detection)
"""

from dataclasses import dataclass
from typing import List
import pandas as pd

from core.structure import Pivot, find_price_pivots


@dataclass
class Level:
    kind: str        # 'ORB_HIGH' | 'ORB_LOW' | 'PDH' | 'PDL' | 'PWH' | 'PWL' | 'SWING_HIGH' | 'SWING_LOW'
    price: float
    formed_pos: int    # bar index from which this level becomes live/testable
    label: str


def _is_high_kind(kind: str) -> bool:
    return kind in ("ORB_HIGH", "PDH", "PWH", "SWING_HIGH", "EQH")


def build_orb_levels(df: pd.DataFrame, orb_minutes: int) -> List[Level]:
    levels: List[Level] = []
    dates = pd.Series(df.index.normalize()).unique()
    for d in dates:
        day_mask = df.index.normalize() == d
        day_df = df[day_mask]
        if len(day_df) < 2:
            continue
        session_start = day_df.index[0]
        orb_end_time = session_start + pd.Timedelta(minutes=orb_minutes)
        orb_df = day_df[day_df.index <= orb_end_time]
        if len(orb_df) < 2:
            continue
        formed_pos = df.index.get_loc(orb_df.index[-1])
        if not isinstance(formed_pos, int):
            continue
        label_suffix = f"{session_start.strftime('%d-%b %H:%M')}-{orb_end_time.strftime('%H:%M')}"
        levels.append(Level("ORB_HIGH", float(orb_df["High"].max()), formed_pos, f"ORB High ({label_suffix})"))
        levels.append(Level("ORB_LOW", float(orb_df["Low"].min()), formed_pos, f"ORB Low ({label_suffix})"))
    return levels


def build_prev_day_levels(df: pd.DataFrame) -> List[Level]:
    levels: List[Level] = []
    day_key = df.index.normalize()
    daily_high = df["High"].groupby(day_key).max()
    daily_low = df["Low"].groupby(day_key).min()
    dates = list(daily_high.index)
    for i in range(1, len(dates)):
        cur_date = dates[i]
        day_mask = day_key == cur_date
        day_bars = df[day_mask]
        if day_bars.empty:
            continue
        formed_pos = df.index.get_loc(day_bars.index[0])
        if not isinstance(formed_pos, int):
            continue
        prev_label = dates[i - 1].strftime("%d-%b")
        levels.append(Level("PDH", float(daily_high.iloc[i - 1]), formed_pos, f"Prev Day High ({prev_label})"))
        levels.append(Level("PDL", float(daily_low.iloc[i - 1]), formed_pos, f"Prev Day Low ({prev_label})"))
    return levels


def build_prev_week_levels(df: pd.DataFrame) -> List[Level]:
    levels: List[Level] = []
    week_key = df.index.to_period("W")
    weekly_high = df["High"].groupby(week_key).max()
    weekly_low = df["Low"].groupby(week_key).min()
    weeks = list(weekly_high.index)
    for i in range(1, len(weeks)):
        cur_week = weeks[i]
        week_mask = week_key == cur_week
        week_bars = df[week_mask]
        if week_bars.empty:
            continue
        formed_pos = df.index.get_loc(week_bars.index[0])
        if not isinstance(formed_pos, int):
            continue
        prev_label = str(weeks[i - 1])
        levels.append(Level("PWH", float(weekly_high.iloc[i - 1]), formed_pos, f"Prev Week High ({prev_label})"))
        levels.append(Level("PWL", float(weekly_low.iloc[i - 1]), formed_pos, f"Prev Week Low ({prev_label})"))
    return levels


def build_swing_levels(df: pd.DataFrame, left: int, right: int, max_levels: int, pivots=None) -> List[Level]:
    if pivots is None:
        pivots = find_price_pivots(df["Close"], left, right)
    highs = [p for p in pivots if p.kind == "H"][-max_levels:]
    lows = [p for p in pivots if p.kind == "L"][-max_levels:]
    levels: List[Level] = []
    for p in highs:
        levels.append(Level("SWING_HIGH", p.price, p.pos, f"Swing High ({p.timestamp})"))
    for p in lows:
        levels.append(Level("SWING_LOW", p.price, p.pos, f"Swing Low ({p.timestamp})"))
    return levels


def build_equal_levels(pivots, tolerance_pct: float = 0.001) -> List[Level]:
    """Clusters nearby swing highs (or lows) within tolerance_pct of each other
    into Equal-High / Equal-Low liquidity pools — classic SMC retail-liquidity zones
    (the same EQH/EQL concept from the Satya Trading SMC notes)."""
    highs = sorted([p for p in pivots if p.kind == "H"], key=lambda p: p.pos)
    lows = sorted([p for p in pivots if p.kind == "L"], key=lambda p: p.pos)
    out: List[Level] = []

    def _cluster(points, kind):
        used = set()
        for i, p1 in enumerate(points):
            if i in used:
                continue
            group = [p1]
            for j in range(i + 1, len(points)):
                if j in used:
                    continue
                p2 = points[j]
                if p1.price != 0 and abs(p2.price - p1.price) / abs(p1.price) <= tolerance_pct:
                    group.append(p2)
                    used.add(j)
            if len(group) >= 2:
                avg_price = sum(g.price for g in group) / len(group)
                last_pos = max(g.pos for g in group)
                out.append(Level(kind, avg_price, last_pos, f"{kind} liquidity pool ({len(group)}x touch)"))

    _cluster(highs, "EQH")
    _cluster(lows, "EQL")
    return out


def build_all_levels(
    df: pd.DataFrame,
    is_intraday: bool,
    orb_minutes: int,
    enable_orb: bool,
    enable_pdh_pdl: bool,
    enable_pwh_pwl: bool,
    enable_swing: bool,
    swing_left: int,
    swing_right: int,
    max_swing_levels: int,
    enable_eq_levels: bool = True,
    eq_tolerance_pct: float = 0.001,
) -> List[Level]:
    levels: List[Level] = []
    if is_intraday:
        if enable_orb:
            levels += build_orb_levels(df, orb_minutes)
        if enable_pdh_pdl:
            levels += build_prev_day_levels(df)
        if enable_pwh_pwl:
            levels += build_prev_week_levels(df)

    pivots = None
    if enable_swing or enable_eq_levels:
        pivots = find_price_pivots(df["Close"], swing_left, swing_right)
    if enable_swing:
        levels += build_swing_levels(df, swing_left, swing_right, max_swing_levels, pivots=pivots)
    if enable_eq_levels:
        levels += build_equal_levels(pivots, eq_tolerance_pct)
    return levels
