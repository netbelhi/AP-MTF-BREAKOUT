# -*- coding: utf-8 -*-
"""
Builds the candlestick + volume chart (Plotly) for one symbol/timeframe,
overlaying tested levels (ORB/PDH/PDL/PWH/PWL/Swing), SMC zones (Order
Blocks, FVGs), breakout/false-breakout markers, and an optional
Entry/SL/Target trade-plan overlay.
"""

from typing import List

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

COLORS = {
    "bg": "#0a0e14", "grid": "#1f2937", "text": "#e6edf3",
    "bull": "#17c384", "bear": "#ff5470", "accent": "#00e5a0", "accent2": "#3ea6ff",
    "gold": "#f0b90b", "ob_bull": "rgba(23,195,132,0.14)", "ob_bear": "rgba(255,84,112,0.14)",
    "fvg_bull": "rgba(0,229,160,0.08)", "fvg_bear": "rgba(255,84,112,0.08)",
    "level": "#8b98a5",
}

STATUS_COLOR = {"Confirmed": "#00e5a0", "False": "#ff5470", "Pending": "#f0b90b"}
STATUS_SYMBOL = {"Confirmed": "triangle-up", "False": "x", "Pending": "circle"}


def build_chart(
    df: pd.DataFrame,
    fvgs: List,
    obs: List,
    levels: List,
    events: List,
    patterns: List = None,
    trade_plan=None,
    max_bars: int = 220,
    title: str = "",
):
    plot_df = df.tail(max_bars)
    start_pos = len(df) - len(plot_df)

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, row_heights=[0.78, 0.22],
        vertical_spacing=0.03,
    )

    fig.add_trace(
        go.Candlestick(
            x=plot_df.index, open=plot_df["Open"], high=plot_df["High"],
            low=plot_df["Low"], close=plot_df["Close"],
            increasing_line_color=COLORS["bull"], decreasing_line_color=COLORS["bear"],
            increasing_fillcolor=COLORS["bull"], decreasing_fillcolor=COLORS["bear"],
            name="Price",
        ),
        row=1, col=1,
    )

    if "Volume" in plot_df.columns:
        vol_colors = [
            COLORS["bull"] if c >= o else COLORS["bear"]
            for o, c in zip(plot_df["Open"], plot_df["Close"])
        ]
        fig.add_trace(
            go.Bar(x=plot_df.index, y=plot_df["Volume"], marker_color=vol_colors, name="Volume"),
            row=2, col=1,
        )

    # --- Order Block + FVG zones ---
    for ob in obs:
        if ob.pos < start_pos or ob.mitigated:
            continue
        x0 = plot_df.index[ob.pos - start_pos]
        fig.add_shape(
            type="rect", x0=x0, x1=plot_df.index[-1], y0=ob.bottom, y1=ob.top,
            fillcolor=COLORS["ob_bull"] if ob.kind == "bullish" else COLORS["ob_bear"],
            line=dict(width=0), row=1, col=1, layer="below",
        )
    for f in [z for z in fvgs if z.pos >= start_pos][-15:]:
        x0 = plot_df.index[f.pos - start_pos]
        x1 = plot_df.index[min(f.pos - start_pos + 12, len(plot_df) - 1)]
        fig.add_shape(
            type="rect", x0=x0, x1=x1, y0=f.bottom, y1=f.top,
            fillcolor=COLORS["fvg_bull"] if f.kind == "bullish" else COLORS["fvg_bear"],
            line=dict(width=0.5, color=COLORS["grid"]), row=1, col=1, layer="below",
        )

    # --- Level lines ---
    for lvl in levels:
        if lvl.formed_pos < start_pos - 1:
            continue
        x0 = plot_df.index[max(lvl.formed_pos - start_pos, 0)]
        fig.add_shape(
            type="line", x0=x0, x1=plot_df.index[-1], y0=lvl.price, y1=lvl.price,
            line=dict(color=COLORS["level"], width=1, dash="dot"), row=1, col=1,
        )
        fig.add_annotation(
            x=x0, y=lvl.price, text=lvl.kind, showarrow=False,
            font=dict(size=9, color=COLORS["level"]), xanchor="left", yanchor="bottom",
            row=1, col=1,
        )

    # --- Candlestick pattern markers (small triangles above/below the candle) ---
    PATTERN_COLOR = {"bullish": COLORS["bull"], "bearish": COLORS["bear"], "neutral": COLORS["level"]}
    for p in (patterns or []):
        if p.pos < start_pos:
            continue
        x = plot_df.index[p.pos - start_pos]
        if p.bias == "bullish":
            y = plot_df["Low"].iloc[p.pos - start_pos] * 0.999
            sym = "triangle-up"
        elif p.bias == "bearish":
            y = plot_df["High"].iloc[p.pos - start_pos] * 1.001
            sym = "triangle-down"
        else:
            y = plot_df["High"].iloc[p.pos - start_pos] * 1.001
            sym = "diamond"
        fig.add_trace(go.Scatter(
            x=[x], y=[y], mode="markers", marker=dict(size=7, color=PATTERN_COLOR[p.bias], symbol=sym, opacity=0.85),
            name=p.pattern, showlegend=False, hovertext=p.pattern, hoverinfo="text+x",
        ), row=1, col=1)

    # --- Breakout / false-breakout markers ---
    for e in events:
        if e.test_pos < start_pos:
            continue
        color = STATUS_COLOR.get(e.status, "#8b98a5")
        sym = STATUS_SYMBOL.get(e.status, "circle")
        x = plot_df.index[e.test_pos - start_pos]
        fig.add_trace(go.Scatter(
            x=[x], y=[e.test_price], mode="markers",
            marker=dict(size=11, color=color, symbol=sym, line=dict(width=1, color="#0a0e14")),
            name=f"{e.level.kind} {e.status}", showlegend=True,
        ), row=1, col=1)

    # --- Trade plan overlay ---
    if trade_plan is not None:
        tp = trade_plan
        for y, label, color in [
            (tp.entry, f"Entry {tp.entry:.2f}", COLORS["accent2"]),
            (tp.stop_loss, f"SL {tp.stop_loss:.2f}", COLORS["bear"]),
            (tp.target1, f"T1 {tp.target1:.2f} ({tp.rr1:.1f}R)", COLORS["gold"]),
            (tp.target2, f"T2 {tp.target2:.2f} ({tp.rr2:.1f}R)", COLORS["bull"]),
        ]:
            fig.add_hline(
                y=y, line=dict(color=color, width=1.3, dash="dash"),
                annotation_text=label, annotation_position="right",
                annotation_font=dict(color=color, size=11), row=1, col=1,
            )

    fig.update_layout(
        height=580, template="plotly_dark",
        paper_bgcolor=COLORS["bg"], plot_bgcolor=COLORS["bg"],
        font=dict(color=COLORS["text"]), title=title,
        margin=dict(l=10, r=10, t=40, b=10),
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(size=9)),
        hovermode="x unified",
    )
    fig.update_yaxes(title_text="Price", row=1, col=1, gridcolor=COLORS["grid"])
    fig.update_yaxes(title_text="Volume", row=2, col=1, gridcolor=COLORS["grid"])
    fig.update_xaxes(gridcolor=COLORS["grid"])
    return fig
