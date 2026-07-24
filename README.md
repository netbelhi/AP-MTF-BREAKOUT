# Satya Trading — MTF Breakout / False-Breakout Notifier

Live-market breakout aur false-breakout (liquidity sweep) scanner —
**NIFTY 50, BANK NIFTY, SENSEX**, sectoral indices, aur NSE stocks — 1m se 1d
tak multi-timeframe, MTF (HTF trend + Order Block/FVG) confluence ke saath,
Entry/SL/Target trade plans aur Telegram alerts.

Ye tool teen proven cheezon ko combine karta hai:
1. **Opening Range Breakout (ORB)** — pehle N minute ka range
2. **False breakout / liquidity sweep detection** (SMC concept) — wick-rejection ya breakout-trap
3. **Multi-timeframe structure confluence** — HTF trend + Order Block + FVG

## Setup

```bash
pip install -r requirements.txt
streamlit run app.py
```

Browser mein `http://localhost:8501` khul jayega.

## Kya detect hota hai

| Level type | Kya hai |
|---|---|
| **ORB High/Low** | Din ke pehle N minute (default 15) ka high/low |
| **PDH/PDL** | Pichle din ka high/low |
| **PWH/PWL** | Pichle hafte ka high/low |
| **Swing High/Low** | Recent structural pivot points (sabhi timeframes, daily bhi) |
| **EQH/EQL** | Equal Highs/Equal Lows — 2+ swing points ek-dusre ke bahut kareeb, liquidity pool (retail stop-losses yahan cluster hote hain) |

Har level ke pehle "test" (jab price usse touch kare) par status milta hai:

| Status | Matlab | Trade |
|---|---|---|
| 🟢 **Confirmed** | Candle level ke paar close hui + agle confirmation bar(s) bhi wahi taraf | Breakout ki **direction mein** (continuation) |
| 🔴 **False** | Wick ne level tod diya par close wapas andar aaya, YA breakout close hone ke baad price wapas cross ho gayi (trap) | Breakout ki **ulti direction mein** (fade the sweep) |
| 🟡 **Pending** | Abhi confirmation ke poore bars nahi mile | Sirf preview — abhi trade mat lo |

Sirf **Confirmed** aur **False** (jab naye hon) hi Telegram alert aur
duplicate-suppression mein count hote hain.

## Entry / Stop Loss / Targets

- **Confirmed Breakout**: Entry = breakout candle ka close, SL = level ke thoda paar (jis taraf se toda), Targets 1.5R/3R breakout ki direction mein.
- **False Breakout**: Entry = rejection candle ka close, SL = wick ke extreme ke thoda paar (jahan sweep hua), Targets 1.5R/3R ulti direction mein.

Ye suggestions hain, financial advice nahi — apna risk khud manage karo
(1-2% per trade khud ke account par, 0.25-1% funded account par).

## MTF Confluence

Har signal ko teen cheezon se check kiya jata hai (score 0-3):
1. **HTF (daily) trend** signal ki direction se match kare
2. **Order Block** (unmitigated) signal ke entry price ke paas ho
3. **FVG** signal ke entry price ke paas ho

🟢🟢 Strong (score ≥2) · 🟡 Partial (score=1) · — (score=0)

## Advanced Price Action

Har signal ko ek independent Price-Action score bhi milta hai (0-3, MTF
confluence se alag):

1. **Candlestick pattern** — Pin Bar (Hammer/Shooting Star), Engulfing, Doji,
   Inside Bar — decision candle par, matching bias ke saath
2. **Wick/Close strength** — False breakout mein wick-rejection ratio, Confirmed
   mein close-strength ratio (default threshold 50%)
3. **Momentum candle** — candle ki range ATR se bada ho (default 1.15x) —
   "Sign of Strength/Weakness" jaisa concept

🔥 Strong (score ≥2) · 🟡 Some (score=1) · — (score=0)

Sidebar se "Sirf Price-Action confirmed signals par alert bhejo" on karke
ise bhi MTF confluence ki tarah filter kar sakte ho.

## Indices covered

Broad: NIFTY 50, BANK NIFTY, SENSEX, NIFTY FIN SERVICE, NIFTY MIDCAP 100
Sectoral: NIFTY IT, AUTO, PHARMA, FMCG, METAL, ENERGY, REALTY, PSU BANK, MEDIA, INFRA

## Timeframes

1m, 2m, 3m (resampled from 1m — yfinance has no native 3m), 5m, 15m, 1h, 1d.
ORB/PDH-PDL/PWH-PWL sirf intraday timeframes (1m-1h) par apply hote hain;
1d par sirf swing-structure levels use hote hain.

## Telegram alerts setup

1. Telegram par **@BotFather** ko `/newbot` bhejo → bot token milega
2. Bot ko ek message bhejo, phir `https://api.telegram.org/bot<TOKEN>/getUpdates`
   khol ke apna chat_id nikaal lo
3. Sidebar mein "Enable Telegram alerts" on karo, token + chat ID daalo

## Duplicate-alert persistence (cloud deploy ke liye)

Local file (`alerted_breakouts.json`) Streamlit Cloud restart par reset ho
sakti hai. Permanent dedup ke liye:
1. GitHub → Settings → Developer settings → Personal access tokens →
   Generate new token (classic) → sirf `gist` scope
2. Sidebar ke "💾 Alert Persistence" section mein token daalke naya Gist banao
3. Milne wala Gist ID + token ko Streamlit Cloud **App Settings → Secrets**
   mein `GITHUB_TOKEN` / `GIST_ID` ke naam se save kar do

## Chart View

Results table ke neeche symbol/timeframe chuno, dikhega:
- Candlestick + Volume panel
- Tested levels (dotted grey lines, label ke saath)
- Order Block / FVG shaded zones
- Breakout markers (🟢 triangle = Confirmed, 🔴 X = False, 🟡 circle = Pending)
- Entry/SL/Target horizontal lines

## Notes

- Sirf har level ka **pehla test** track hota hai (avoid karta hai purani
  repeated news). Agar level baad mein support/resistance ki tarah phir se
  test ho, wo is version mein track nahi hota.
- Index volume (NIFTY/BANKNIFTY/SENSEX) yfinance se 0/unreliable aa sakta
  hai — stocks ka volume zyada meaningful hota hai.
- Live yfinance data ke liye internet chahiye. Agar fail ho, app "SYNTHETIC
  DEMO" badge dikhake fallback kar leta hai — crash nahi karta.

## File structure

```
app.py                     — Streamlit UI + scan loop
core/config.py              — watchlist, timeframes, level/breakout params
core/data.py                  — yfinance fetch + NSE-session-aware synthetic fallback
core/levels.py                 — ORB / PDH-PDL / PWH-PWL / Swing level builders
core/structure.py                — Pivot, FVG, Order Block, BOS/CHoCH, confluence scoring
core/breakout.py                  — breakout/false-breakout detection + trade plan
core/price_action.py                — candlestick patterns, rejection/continuation strength, ATR momentum
core/charting.py                   — Plotly candlestick + volume chart with overlays
core/telegram_alert.py               — Telegram Bot API sender
core/persistence.py                    — duplicate-alert suppression (GitHub Gist + local fallback)
```

---
*Satya Trading — SMC/ICT trading tools series. Sirf educational use ke liye; trading mein risk hai, koi bhi strategy guaranteed profit nahi deti.*
