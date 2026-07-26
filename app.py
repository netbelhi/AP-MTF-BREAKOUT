# -*- coding: utf-8 -*-
"""
Satya Trading — MTF Breakout / False-Breakout Notifier
==========================================================
Detects genuine breakouts vs false breakouts (liquidity sweeps / fakeouts)
against Opening Range, Previous Day/Week High-Low, and swing-structure
levels — across multiple timeframes — for NIFTY/BANKNIFTY/SENSEX/sectoral
indices and NSE stocks. Includes MTF (HTF trend + Order Block/FVG)
confluence, Entry/SL/Target trade plans, and Telegram alerting.

Run:
    pip install -r requirements.txt
    streamlit run app.py
"""

import time
from datetime import datetime

import pandas as pd
import pytz
import streamlit as st

from core import config
from core.data import fetch_candles
from core.levels import build_all_levels
from core.breakout import detect_breakouts, compute_trade_plan, latest_per_level_kind
from core.structure import (
    find_price_pivots, find_fvgs, find_order_blocks,
    detect_structure_events, current_trend, compute_confluence,
)
from core.telegram_alert import send_telegram_message, format_alert
from core import persistence
from core import charting
from core import price_action as pa_mod

IST = pytz.timezone("Asia/Kolkata")

# ---------------------------------------------------------------------------
# Page setup + dark "trading terminal" theme
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Satya Trading — Breakout / False-Breakout Notifier",
    page_icon="⚡",
    layout="wide",
)

st.markdown("""
<style>
:root{
  --bg:#0a0e14; --panel:#10161f; --panel2:#151c27; --accent:#00e5a0; --accent2:#3ea6ff;
  --text:#e6edf3; --muted:#8b98a5; --border:#1f2937; --gold:#f0b90b; --red:#ff5470;
}
.stApp{ background:var(--bg); color:var(--text);}
section[data-testid="stSidebar"]{ background:var(--panel); border-right:1px solid var(--border);}
h1,h2,h3{ color:var(--accent) !important; font-family:'Rajdhani',sans-serif;}
.brandbar{ display:flex; align-items:center; justify-content:space-between;
  background:var(--panel); border:1px solid var(--border); border-radius:10px;
  padding:14px 20px; margin-bottom:18px;}
.brandbar .title{ color:var(--gold); letter-spacing:3px; font-size:13px; text-transform:uppercase;}
.badge{ display:inline-block; padding:4px 12px; border-radius:20px; font-size:12px; font-weight:600; margin-left:8px;}
.badge-open{ background:rgba(0,229,160,0.15); color:var(--accent); border:1px solid var(--accent);}
.badge-closed{ background:rgba(255,84,112,0.15); color:var(--red); border:1px solid var(--red);}
.badge-live{ background:rgba(62,166,255,0.15); color:var(--accent2); border:1px solid var(--accent2);}
.badge-demo{ background:rgba(240,185,11,0.15); color:var(--gold); border:1px solid var(--gold);}
.stDataFrame{ border:1px solid var(--border);}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="brandbar">
  <div><div class="title">Satya Trading</div>
       <div style="font-size:22px;font-weight:700;color:#e6edf3;">MTF Breakout / False-Breakout Notifier</div></div>
  <div style="text-align:right;color:#8b98a5;font-size:12px;">ORB · PDH-PDL · PWH-PWL · Swing Structure</div>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Sidebar controls
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### 🎯 Watchlist")
    sel_indices = st.multiselect(
        "Indices", list(config.INDEX_SYMBOLS.keys()), default=config.DEFAULT_INDEX_SELECTION,
    )
    sel_stocks = st.multiselect(
        "NSE Stocks", config.DEFAULT_STOCK_WATCHLIST, default=config.DEFAULT_STOCK_WATCHLIST[:6],
    )
    extra_symbol = st.text_input("+ Add custom NSE symbol (e.g. DMART.NS)", "")

    st.markdown("### ⏱️ Timeframes")
    sel_timeframes = st.multiselect(
        "Scan on", list(config.TIMEFRAMES.keys()), default=config.DEFAULT_TIMEFRAMES,
    )

    st.markdown("### 📐 Levels")
    orb_minutes = st.slider("Opening Range minutes", 5, 60, config.ORB_MINUTES, step=5)
    enable_orb = st.checkbox("Opening Range (ORB)", value=config.ENABLE_ORB)
    enable_pdh_pdl = st.checkbox("Previous Day High/Low", value=config.ENABLE_PDH_PDL)
    enable_pwh_pwl = st.checkbox("Previous Week High/Low", value=config.ENABLE_PWH_PWL)
    enable_swing = st.checkbox("Swing structure High/Low", value=config.ENABLE_SWING_LEVELS)
    enable_eq_levels = st.checkbox("Equal Highs/Lows (EQH/EQL liquidity pools)", value=config.ENABLE_EQ_LEVELS)
    eq_tolerance_pct = st.slider("EQH/EQL tolerance (%)", 0.05, 0.5, config.EQ_TOLERANCE_PCT * 100, step=0.05) / 100
    swing_lr = st.slider("Swing pivot left/right bars", 2, 6, config.SWING_PIVOT_LEFT)

    st.markdown("### 💥 Breakout Rules")
    confirm_bars = st.slider(
        "Confirmation bars (candles beyond level = Confirmed)", 1, 3, config.CONFIRM_BARS_DEFAULT
    )

    st.markdown("### 🕯️ Price Action")
    atr_period = st.slider("ATR period", 5, 30, config.ATR_PERIOD)
    momentum_multiple = st.slider("Momentum candle threshold (x ATR)", 1.0, 2.0, config.MOMENTUM_ATR_MULTIPLE, step=0.05)
    pa_strength_threshold = st.slider("Wick/close strength threshold", 0.3, 0.8, config.PA_STRENGTH_THRESHOLD, step=0.05)
    require_price_action = st.checkbox(
        "Sirf Price-Action confirmed signals par alert bhejo", value=config.REQUIRE_PRICE_ACTION_DEFAULT
    )
    min_pa_score = st.slider("Min price-action score", 1, 3, config.MIN_PA_SCORE_DEFAULT)

    st.markdown("### 🧩 MTF Confluence")
    smc_lookback = st.slider("Lookback bars for OB/FVG", 10, 80, config.SMC_LOOKBACK_BARS)
    require_confluence = st.checkbox(
        "Sirf MTF-confirmed signals par alert bhejo", value=config.REQUIRE_CONFLUENCE_DEFAULT
    )
    min_conf_score = st.slider("Min confluence score", 1, 3, config.MIN_CONFLUENCE_SCORE_DEFAULT)

    st.markdown("### 💾 Alert Persistence")
    def _secret(key: str) -> str:
        try:
            return st.secrets.get(key, "")
        except Exception:
            return ""

    _secret_token = _secret("GITHUB_TOKEN")
    _secret_gist = _secret("GIST_ID")
    if _secret_token and _secret_gist:
        gh_token, gist_id = _secret_token, _secret_gist
        st.caption("✅ Streamlit Secrets se GitHub Gist mila — cloud-persistent hai.")
    else:
        with st.expander("Cloud par persistent banao (recommended for Streamlit Cloud)", expanded=False):
            st.caption(
                "Local file Streamlit Cloud restart/sleep par reset ho jati hai. Permanent dedup "
                "ke liye GitHub token + Gist ID do — ya best: **App Settings → Secrets** mein "
                "`GITHUB_TOKEN` aur `GIST_ID` ke naam se save kar do."
            )
            gh_token = st.text_input("GitHub Personal Access Token (scope: gist)", type="password")
            gist_id = st.text_input("Gist ID (khaali chodo agar naya banana hai)")
            if gh_token and not gist_id and st.button("🆕 Naya alert-store Gist banao"):
                new_id = persistence.create_gist(gh_token)
                if new_id:
                    gist_id = new_id
                    st.success(f"Gist ban gaya — ID: `{new_id}`. Ise Secrets mein `GIST_ID` ke saath save kar lo.")
                else:
                    st.error("Gist nahi ban paya — token check karo (scope 'gist' hona chahiye).")

    st.markdown("### 📲 Telegram Alerts")
    telegram_enabled = st.checkbox("Enable Telegram alerts", value=False)
    bot_token = st.text_input("Bot token", value=config.TELEGRAM_BOT_TOKEN, type="password")
    chat_id = st.text_input("Chat ID", value=config.TELEGRAM_CHAT_ID)

    st.markdown("### 🔄 Live Scanning")
    live_mode = st.checkbox("Auto-refresh (Live Mode)", value=False)
    refresh_secs = st.slider("Refresh every (sec)", 20, 300, config.AUTO_REFRESH_SECONDS, step=10)
    scan_now = st.button("🔍 Scan Now", use_container_width=True)

# ---------------------------------------------------------------------------
# Build the symbol list
# ---------------------------------------------------------------------------
symbol_map = {name: config.INDEX_SYMBOLS[name] for name in sel_indices}
for s in sel_stocks:
    symbol_map[s.replace(".NS", "")] = s
if extra_symbol.strip():
    sym = extra_symbol.strip().upper()
    if not sym.endswith(".NS") and not sym.startswith("^"):
        sym = sym + ".NS"
    symbol_map[extra_symbol.strip().upper().replace(".NS", "")] = sym

if not symbol_map or not sel_timeframes:
    st.warning("Sidebar se kam se kam ek symbol aur ek timeframe select karo.")
    st.stop()

# ---------------------------------------------------------------------------
# Market status badge (IST)
# ---------------------------------------------------------------------------
now_ist = datetime.now(IST)
open_t = now_ist.replace(hour=9, minute=15, second=0, microsecond=0)
close_t = now_ist.replace(hour=15, minute=30, second=0, microsecond=0)
is_weekday = now_ist.weekday() < 5
market_open = is_weekday and open_t <= now_ist <= close_t

c1, c2, c3 = st.columns([2, 2, 6])
with c1:
    st.markdown(
        f'Market: <span class="badge {"badge-open" if market_open else "badge-closed"}">'
        f'{"OPEN" if market_open else "CLOSED"}</span>', unsafe_allow_html=True,
    )
with c2:
    st.markdown(f"IST time: **{now_ist.strftime('%H:%M:%S')}**")

# ---------------------------------------------------------------------------
# Cached fetch
# ---------------------------------------------------------------------------
@st.cache_data(ttl=config.DATA_CACHE_TTL_SECONDS, show_spinner=False)
def _cached_fetch(symbol: str, interval: str, period: str, resample: str = None):
    return fetch_candles(symbol, interval, period, resample)


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------
alert_store = persistence.get_store(gh_token, gist_id, config.ALERT_LOG_PATH)
alerted_keys = alert_store.load()
rows = []
any_live, any_synthetic = False, False
new_signals_this_scan = []
chart_context = {}   # (label, tf) -> {df, fvgs, obs, levels, events}

progress = st.progress(0.0, text="Scanning...")
total = len(symbol_map) * len(sel_timeframes)
done = 0

for label, symbol in symbol_map.items():
    # HTF (daily) trend context — computed once per symbol, reused across timeframes
    htf_trend = None
    try:
        d_cfg = config.TIMEFRAMES["1d"]
        d_df, d_live = _cached_fetch(symbol, d_cfg["interval"], d_cfg["period"], d_cfg.get("resample"))
        any_live, any_synthetic = any_live or d_live, any_synthetic or (not d_live)
        if d_df is not None and len(d_df) >= (swing_lr * 2 + 5):
            d_pivots = find_price_pivots(d_df["Close"], swing_lr, swing_lr)
            htf_trend = current_trend(detect_structure_events(d_pivots))
    except Exception:
        pass

    for tf in sel_timeframes:
        tf_cfg = config.TIMEFRAMES[tf]
        interval, period, resample = tf_cfg["interval"], tf_cfg["period"], tf_cfg.get("resample")
        is_intraday = tf in config.INTRADAY_TIMEFRAMES
        try:
            df, is_live = _cached_fetch(symbol, interval, period, resample)
            any_live, any_synthetic = any_live or is_live, any_synthetic or (not is_live)
            if df is None or len(df) < (swing_lr * 2 + 10):
                done += 1
                continue

            levels = build_all_levels(
                df, is_intraday, orb_minutes, enable_orb, enable_pdh_pdl, enable_pwh_pwl,
                enable_swing, swing_lr, swing_lr, config.MAX_SWING_LEVELS,
                enable_eq_levels=enable_eq_levels, eq_tolerance_pct=eq_tolerance_pct,
            )
            events = detect_breakouts(df, levels, label, tf, confirm_bars=confirm_bars)
            events = latest_per_level_kind(events, keep_n=12)

            fvgs = find_fvgs(df)
            obs = find_order_blocks(df, fvgs)
            patterns = pa_mod.detect_patterns(df)
            atr = pa_mod.compute_atr(df, atr_period)
            chart_context[(label, tf)] = {
                "df": df, "fvgs": fvgs, "obs": obs, "levels": levels, "events": events, "patterns": patterns,
            }

            for e in events:
                tp = compute_trade_plan(e)
                conf = compute_confluence(
                    e.direction, e.close_price, e.confirm_pos, fvgs, obs, htf_trend,
                    smc_lookback, config.SMC_ZONE_TOLERANCE,
                )

                if e.status == "False":
                    o_, h_, l_, c_ = df["Open"].iloc[e.test_pos], df["High"].iloc[e.test_pos], df["Low"].iloc[e.test_pos], df["Close"].iloc[e.test_pos]
                    strength = pa_mod.rejection_strength(o_, h_, l_, c_, e.direction)
                    pa_pos = e.test_pos
                elif e.status == "Confirmed":
                    o_, h_, l_, c_ = df["Open"].iloc[e.confirm_pos], df["High"].iloc[e.confirm_pos], df["Low"].iloc[e.confirm_pos], df["Close"].iloc[e.confirm_pos]
                    strength = pa_mod.continuation_strength(o_, h_, l_, c_, e.direction)
                    pa_pos = e.confirm_pos
                else:
                    strength, pa_pos = None, e.confirm_pos
                pa_score = pa_mod.compute_price_action_score(
                    e.direction, pa_pos, patterns, df, atr,
                    strength_ratio=strength, strength_threshold=pa_strength_threshold,
                    momentum_multiple=momentum_multiple,
                )

                alertable = e.status in ("Confirmed", "False")
                is_new = alertable and e.signal_key not in alerted_keys
                status_badge = {"Confirmed": "🟢 Confirmed", "False": "🔴 False Breakout", "Pending": "🟡 Pending"}[e.status]

                rows.append({
                    "Symbol": label, "TF": tf, "Level": e.level.kind, "Label": e.level.label,
                    "Status": status_badge, "Bias": "BUY" if e.direction == "bullish" else "SELL",
                    "Level Price": round(e.level.price, 2), "Test Price": round(e.test_price, 2),
                    "Close": round(e.close_price, 2), "MTF": conf.label, "PA": pa_score.label,
                    "Entry": round(tp.entry, 2) if tp else "—",
                    "SL": round(tp.stop_loss, 2) if tp else "—",
                    "T1 (1.5R)": round(tp.target1, 2) if tp else "—",
                    "T2 (3R)": round(tp.target2, 2) if tp else "—",
                    "MTF Tags": "; ".join(conf.tags) if conf.tags else "—",
                    "PA Tags": "; ".join(pa_score.tags) if pa_score.tags else "—",
                    "New": "🆕" if is_new else "",
                })
                if is_new:
                    new_signals_this_scan.append((e, label, tf, tp, conf, pa_score))
                    alerted_keys.add(e.signal_key)
        except Exception as ex:
            rows.append({
                "Symbol": label, "TF": tf, "Level": "-", "Label": f"error: {ex}", "Status": "-",
                "Bias": "-", "Level Price": None, "Test Price": None, "Close": None, "MTF": "-", "PA": "-",
                "Entry": "-", "SL": "-", "T1 (1.5R)": "-", "T2 (3R)": "-", "MTF Tags": "-", "PA Tags": "-", "New": "",
            })
        done += 1
        progress.progress(done / total, text=f"Scanning... {label} [{tf}]")

progress.empty()
save_ok = alert_store.save(alerted_keys)

# ---------------------------------------------------------------------------
# Data-source + persistence badges
# ---------------------------------------------------------------------------
with c3:
    if any_live and not any_synthetic:
        st.markdown('Data: <span class="badge badge-live">LIVE (yfinance)</span>', unsafe_allow_html=True)
    elif any_live and any_synthetic:
        st.markdown('Data: <span class="badge badge-live">LIVE</span> '
                     '<span class="badge badge-demo">+ SYNTHETIC (kuch symbols)</span>', unsafe_allow_html=True)
    else:
        st.markdown('Data: <span class="badge badge-demo">SYNTHETIC DEMO — no internet/yfinance in this environment</span>',
                     unsafe_allow_html=True)
    persist_cls = "badge-live" if isinstance(alert_store, persistence.GistStore) else "badge-demo"
    st.markdown(f'Dedup storage: <span class="badge {persist_cls}">{alert_store.backend_name}</span>',
                unsafe_allow_html=True)
    if not save_ok:
        st.caption("⚠️ Alert store save fail hua is scan mein — agla scan retry karega.")

# ---------------------------------------------------------------------------
# Telegram alerts
# ---------------------------------------------------------------------------
if telegram_enabled and new_signals_this_scan:
    to_send = new_signals_this_scan
    if require_confluence:
        to_send = [t for t in to_send if t[4].score >= min_conf_score]
    if require_price_action:
        to_send = [t for t in to_send if t[5].score >= min_pa_score]
    skipped = len(new_signals_this_scan) - len(to_send)
    if skipped:
        st.caption(f"ℹ️ {skipped} naya signal mila but MTF/Price-Action threshold na milne ki wajah se alert skip hua.")
    for e, label, tf, tp, conf, pa_score in to_send:
        msg = format_alert(e, label, tf, trade_plan=tp, confluence=conf, price_action=pa_score)
        ok, info = send_telegram_message(bot_token, chat_id, msg)
        if not ok:
            st.toast(f"Telegram bhej nahi paya ({label} {tf}): {info}", icon="⚠️")
elif new_signals_this_scan and not telegram_enabled:
    st.info(f"{len(new_signals_this_scan)} naya breakout/false-breakout signal mila — Telegram alerts abhi off hain (sidebar se on karo).")

# ---------------------------------------------------------------------------
# Results table
# ---------------------------------------------------------------------------
st.markdown("### 📊 Active Breakout / False-Breakout Signals")
if rows:
    result_df = pd.DataFrame(rows)
    result_df = result_df.sort_values("New", ascending=False)

    def _style_bias(v):
        if v == "BUY":
            return "color:#00e5a0;font-weight:700;"
        if v == "SELL":
            return "color:#ff5470;font-weight:700;"
        return ""

    styler = result_df.style
    style_fn = getattr(styler, "map", None) or styler.applymap
    st.dataframe(
        style_fn(_style_bias, subset=["Bias"]),
        use_container_width=True, hide_index=True, height=min(60 + 35 * len(result_df), 600),
    )
    if new_signals_this_scan:
        st.success(f"✅ Is scan mein {len(new_signals_this_scan)} NAYA signal mila (🆕 marked).")
else:
    st.info("Abhi koi breakout/false-breakout signal nahi mila selected watchlist/timeframes par.")

# ---------------------------------------------------------------------------
# Chart view
# ---------------------------------------------------------------------------
st.markdown("### 📈 Chart View")
if chart_context:
    chart_keys = list(chart_context.keys())

    def _chart_key_label(k):
        lbl, tf = k
        n_events = len(chart_context[k]["events"])
        return f"{lbl} — {tf}" + (f"  ({n_events} events)" if n_events else "")

    default_idx = 0
    for i, k in enumerate(chart_keys):
        if any(ev.status in ("Confirmed", "False") for ev in chart_context[k]["events"]):
            default_idx = i
            break

    chosen = st.selectbox("Symbol — Timeframe chuno", chart_keys, index=default_idx, format_func=_chart_key_label)
    ctx = chart_context[chosen]

    tp, tp_event = None, None
    actionable = [e for e in ctx["events"] if e.status in ("Confirmed", "False")]
    pick_from = actionable or ctx["events"]
    if pick_from:
        tp_event = max(pick_from, key=lambda e: e.confirm_pos)
        tp = compute_trade_plan(tp_event)

    fig = charting.build_chart(
        ctx["df"], ctx["fvgs"], ctx["obs"], ctx["levels"], ctx["events"], patterns=ctx.get("patterns"),
        trade_plan=tp, title=f"{chosen[0]} — {chosen[1]}",
    )
    st.plotly_chart(fig, use_container_width=True)

    if tp:
        st.caption(
            f"Trade plan **{tp_event.level.kind} {tp_event.status}** ({'BUY' if tp_event.direction=='bullish' else 'SELL'}) "
            f"basis: **{tp.basis}** — Entry `{tp.entry:.2f}` · SL `{tp.stop_loss:.2f}` · "
            f"T1 `{tp.target1:.2f}` (1.5R) · T2 `{tp.target2:.2f}` (3R). "
            "Yeh suggestion hai, apna risk khud manage karo."
        )
    st.caption(
        "Dotted grey lines = tested levels (ORB/PDH/PDL/PWH/PWL/Swing). "
        "🟢 triangle = Confirmed breakout · 🔴 X = False breakout (liquidity sweep) · 🟡 circle = Pending. "
        "Shaded boxes = Order Block / FVG zones."
    )
else:
    st.info("Chart dekhne ke liye pehle 'Scan Now' se kam se kam ek symbol/timeframe scan karo.")

st.caption(
    "Confirmed = breakout ke direction mein trade (continuation). False = breakout fail hua, "
    "ulti direction mein trade (liquidity sweep/fakeout fade). Pending = abhi confirmation bars ka wait hai."
)

with st.expander("ℹ️ Kaise kaam karta hai"):
    st.markdown("""
- **Levels**: Opening Range High/Low (pehle N minute), Previous Day High/Low, Previous Week High/Low, aur recent Swing structure High/Low — sabko test karta hai.
- **Confirmed Breakout** 🟢: candle level ke paar close hui aur agle `confirm_bars` candles bhi wahi taraf close hue — trade **breakout ki direction mein**.
- **False Breakout / Liquidity Sweep** 🔴: ya to candle ne wick se level tod diya par close wapas andar aa gaya (turant sweep), ya breakout close hone ke baad agla candle wapas cross ho gaya (trap) — trade **ulti direction mein** (fade).
- **Pending** 🟡: abhi confirmation ke liye poore bars nahi mile — preview hai, badal sakta hai.
- **MTF Confluence**: HTF (daily) trend alignment + Order Block + FVG — teeno match karein to zyada score.
- **Price Action Score** 🔥: candle ka pattern (Pin Bar/Engulfing), wick-rejection ya close-strength ratio (≥ threshold), aur ATR-se-bada "momentum candle" (Sign of Strength) — teeno match karein to zyada score. Ye MTF confluence se alag, independent score hai.
- **EQH/EQL (Equal Highs/Lows)**: 2+ swing points jo ek-dusre ke bahut kareeb hon, unhe liquidity pool maana jata hai — jaisa tumhari SMC notes mein tha, retail stop-losses yahin cluster hote hain.
- **Entry/SL/Target**: Confirmed mein SL level ke paar, False mein SL wick ke paar (jahan sweep hua). Targets 1.5R aur 3R par.
- Sirf **Confirmed/False + naye (🆕)** signals hi Telegram alert karte hain — Pending sirf info ke liye hai.
- **Live Mode**: on karne par app har `refresh_secs` seconds mein khud-ba-khud re-scan karta hai.
""")

# ---------------------------------------------------------------------------
# Auto-refresh (Live Mode)
# ---------------------------------------------------------------------------
if live_mode:
    st.caption(f"⏳ Agla auto-scan {refresh_secs}s mein...")
    time.sleep(refresh_secs)
    st.rerun()
