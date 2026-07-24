# -*- coding: utf-8 -*-
"""
Satya Trading — MTF Breakout / False-Breakout Notifier
Configuration: watchlist, timeframes, level/breakout params, Telegram settings.
"""

# --------------------------------------------------------------------------
# Indices (Yahoo Finance symbols) — broad + sectoral
# --------------------------------------------------------------------------
INDEX_SYMBOLS = {
    "NIFTY 50":            "^NSEI",
    "BANK NIFTY":          "^NSEBANK",
    "SENSEX":              "^BSESN",
    "NIFTY FIN SERVICE":   "^CNXFIN",
    "NIFTY MIDCAP 100":    "^NSEMDCP50",
    "NIFTY IT":            "^CNXIT",
    "NIFTY AUTO":          "^CNXAUTO",
    "NIFTY PHARMA":        "^CNXPHARMA",
    "NIFTY FMCG":          "^CNXFMCG",
    "NIFTY METAL":         "^CNXMETAL",
    "NIFTY ENERGY":        "^CNXENERGY",
    "NIFTY REALTY":        "^CNXREALTY",
    "NIFTY PSU BANK":      "^CNXPSUBANK",
    "NIFTY MEDIA":         "^CNXMEDIA",
    "NIFTY INFRA":         "^CNXINFRA",
}
DEFAULT_INDEX_SELECTION = ["NIFTY 50", "BANK NIFTY", "SENSEX"]

DEFAULT_STOCK_WATCHLIST = [
    "RELIANCE.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS", "TCS.NS",
    "SBIN.NS", "AXISBANK.NS", "KOTAKBANK.NS", "LT.NS", "ITC.NS",
    "BHARTIARTL.NS", "HINDUNILVR.NS", "BAJFINANCE.NS", "MARUTI.NS",
    "SUNPHARMA.NS", "TATAMOTORS.NS", "TATASTEEL.NS", "ADANIENT.NS",
    "ASIANPAINT.NS", "WIPRO.NS", "HCLTECH.NS", "ULTRACEMCO.NS",
    "TITAN.NS", "NTPC.NS", "POWERGRID.NS",
]

# --------------------------------------------------------------------------
# Timeframes: label -> {interval, period, resample}
# yfinance has no native "3m" interval — built by resampling 1m candles.
# --------------------------------------------------------------------------
TIMEFRAMES = {
    "1m":  {"interval": "1m",  "period": "5d",  "resample": None},
    "2m":  {"interval": "2m",  "period": "5d",  "resample": None},
    "3m":  {"interval": "1m",  "period": "5d",  "resample": "3min"},
    "5m":  {"interval": "5m",  "period": "5d",  "resample": None},
    "15m": {"interval": "15m", "period": "10d", "resample": None},
    "1h":  {"interval": "60m", "period": "60d", "resample": None},
    "1d":  {"interval": "1d",  "period": "1y",  "resample": None},
}
DEFAULT_TIMEFRAMES = ["1m", "2m", "3m", "5m", "15m"]

# Intraday timeframes only — ORB / PDH-PDL / PWH-PWL only make sense here.
# "1d" candles get swing-structure levels only.
INTRADAY_TIMEFRAMES = ["1m", "2m", "3m", "5m", "15m", "1h"]

# --------------------------------------------------------------------------
# Level detection
# --------------------------------------------------------------------------
ORB_MINUTES = 15                 # opening-range window from market open (09:15 IST)
ENABLE_ORB = True
ENABLE_PDH_PDL = True
ENABLE_PWH_PWL = True
ENABLE_SWING_LEVELS = True

SWING_PIVOT_LEFT = 3
SWING_PIVOT_RIGHT = 3
MAX_SWING_LEVELS = 4             # most recent N swing highs + N swing lows to track per scan

ENABLE_EQ_LEVELS = True           # Equal Highs / Equal Lows liquidity pools
EQ_TOLERANCE_PCT = 0.001            # 0.1% — how close swing points must be to count as "equal"

# --------------------------------------------------------------------------
# Advanced price action — candlestick patterns, rejection/continuation
# strength, ATR-based momentum ("Sign of Strength / Sign of Weakness")
# --------------------------------------------------------------------------
ATR_PERIOD = 14
MOMENTUM_ATR_MULTIPLE = 1.15        # candle range >= this x ATR = momentum/SOS candle
PA_STRENGTH_THRESHOLD = 0.5           # wick/close ratio needed to count as "strong"
REQUIRE_PRICE_ACTION_DEFAULT = False
MIN_PA_SCORE_DEFAULT = 1

# --------------------------------------------------------------------------
# Breakout / false-breakout classification
# --------------------------------------------------------------------------
CONFIRM_BARS_DEFAULT = 1          # candles beyond the level needed to call it "Confirmed"
LEVEL_BUFFER_PCT = 0.0015          # small buffer used for SL placement beyond a level/wick

# --------------------------------------------------------------------------
# MTF / SMC confluence (HTF trend + Order Block + FVG)
# --------------------------------------------------------------------------
SMC_LOOKBACK_BARS = 30
SMC_ZONE_TOLERANCE = 0.002
REQUIRE_CONFLUENCE_DEFAULT = False
MIN_CONFLUENCE_SCORE_DEFAULT = 1

# --------------------------------------------------------------------------
# Telegram (leave blank — set from sidebar or Streamlit Secrets)
# --------------------------------------------------------------------------
TELEGRAM_BOT_TOKEN = ""
TELEGRAM_CHAT_ID = ""

# --------------------------------------------------------------------------
# Refresh & storage
# --------------------------------------------------------------------------
AUTO_REFRESH_SECONDS = 60
DATA_CACHE_TTL_SECONDS = 45
ALERT_LOG_PATH = "alerted_breakouts.json"
