# -*- coding: utf-8 -*-
"""
Data layer: fetches OHLC candles via yfinance for the requested symbol +
timeframe. If yfinance / network is unavailable, falls back to a seeded
synthetic random-walk series (clearly labelled in the UI) so the app and
its breakout logic can still be exercised end-to-end.

Also handles resampling: yfinance has no native "3m" interval, so a 3-minute
timeframe is built by fetching 1m candles and resampling them to 3-minute bars.
"""

import hashlib
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd

try:
    import yfinance as yf
    _HAS_YFINANCE = True
except Exception:
    _HAS_YFINANCE = False

_FREQ_MINUTES = {
    "1m": 1, "2m": 2, "3min": 3, "5m": 5, "15m": 15, "60m": 60, "1d": 24 * 60,
}


def _seed_from(symbol: str, label: str) -> int:
    h = hashlib.sha256(f"{symbol}:{label}".encode()).hexdigest()
    return int(h[:8], 16)


def _resample_ohlc(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last"}
    if "Volume" in df.columns:
        agg["Volume"] = "sum"
    out = df.resample(rule, label="right", closed="right").agg(agg)
    return out.dropna(subset=["Close"])


def _synthetic_candles(symbol: str, label: str, bars: int = 500) -> pd.DataFrame:
    """Deterministic pseudo-random walk scaled roughly like Indian index/stock prices,
    used only when live data can't be reached (no internet in this environment).
    Builds bars during NSE trading hours (09:15-15:30 IST) across consecutive
    weekdays, so opening-range / previous-day-level logic behaves realistically."""
    rng = np.random.default_rng(_seed_from(symbol, label))

    base_price = {
        "^NSEI": 24500, "^NSEBANK": 51500, "^BSESN": 80500, "^CNXFIN": 23500,
    }.get(symbol, 1500 + (hash(symbol) % 3000))

    step_minutes = _FREQ_MINUTES.get(label, 60)
    vol = 0.0016 if step_minutes < 24 * 60 else 0.011
    if step_minutes < 5:
        vol = vol * max(0.45, (step_minutes / 5.0) ** 0.5)

    if step_minutes >= 24 * 60:
        idx = pd.bdate_range(end=datetime.now(), periods=bars)
    else:
        bars_per_day = max(1, (375 // step_minutes))
        n_days = max(1, bars // bars_per_day + 2)
        all_ts = []
        day = pd.Timestamp.now().normalize()
        d = 0
        while len(all_ts) < bars:
            candidate_day = day - pd.tseries.offsets.BDay(n_days - d)
            day_start = candidate_day + pd.Timedelta(hours=9, minutes=15)
            day_ts = pd.date_range(day_start, periods=bars_per_day, freq=f"{step_minutes}min")
            all_ts.extend(list(day_ts))
            d += 1
            if d > n_days + 5:
                break
        idx = pd.DatetimeIndex(sorted(all_ts)[-bars:])
        bars = len(idx)

    rets = rng.normal(0, vol, bars)
    trend = np.sin(np.linspace(0, 6.5, bars)) * vol * 3
    rets = rets + trend / bars
    close = base_price * np.cumprod(1 + rets)

    high = close * (1 + np.abs(rng.normal(0, vol * 0.6, bars)))
    low = close * (1 - np.abs(rng.normal(0, vol * 0.6, bars)))
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    volume = rng.integers(50_000, 2_000_000, bars)

    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=idx,
    )


def fetch_candles(
    symbol: str, interval: str, period: str, resample: Optional[str] = None
) -> tuple:
    """Returns (dataframe, is_live). is_live=False means synthetic fallback was used."""
    effective_label = resample or interval

    if _HAS_YFINANCE:
        try:
            df = yf.download(
                symbol, interval=interval, period=period,
                progress=False, auto_adjust=True, threads=False,
            )
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [c[0] for c in df.columns]
            if df is not None and len(df) >= 30:
                df = df.dropna(subset=["Close"])
                if resample:
                    df = _resample_ohlc(df, resample)
                if len(df) >= 20:
                    return df, True
        except Exception:
            pass
    return _synthetic_candles(symbol, effective_label), False
