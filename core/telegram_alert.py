# -*- coding: utf-8 -*-
"""Minimal Telegram Bot API wrapper for sending breakout/false-breakout alerts."""

import requests


def send_telegram_message(bot_token: str, chat_id: str, text: str) -> tuple:
    if not bot_token or not chat_id:
        return False, "Bot token / chat ID missing"
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        resp = requests.post(
            url, data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}, timeout=8,
        )
        if resp.status_code == 200 and resp.json().get("ok"):
            return True, "sent"
        return False, f"Telegram API error: {resp.status_code} {resp.text[:200]}"
    except Exception as e:
        return False, f"Network/Telegram error: {e}"


def format_alert(event, symbol_label: str, timeframe: str, trade_plan=None, confluence=None, price_action=None) -> str:
    status_icon = {"Confirmed": "🟢", "False": "🔴", "Pending": "🟡"}.get(event.status, "⚪")
    bias_word = "BUY" if event.direction == "bullish" else "SELL"
    msg = (
        f"<b>Satya Trading — Breakout Alert</b>\n"
        f"{status_icon} <b>{event.status}</b>  |  {event.level.kind}  |  {bias_word}\n"
        f"Symbol: <b>{symbol_label}</b>\n"
        f"Timeframe: <b>{timeframe}</b>\n"
        f"Level: {event.level.label} @ {event.level.price:.2f}\n"
        f"Test price: {event.test_price:.2f} → Close: {event.close_price:.2f}\n"
    )
    if trade_plan is not None:
        msg += (
            f"Entry: {trade_plan.entry:.2f} | SL: {trade_plan.stop_loss:.2f}\n"
            f"T1: {trade_plan.target1:.2f} ({trade_plan.rr1:.1f}R) | "
            f"T2: {trade_plan.target2:.2f} ({trade_plan.rr2:.1f}R)\n"
        )
    if confluence is not None:
        msg += f"MTF: <b>{confluence.label}</b>\n"
        for tag in confluence.tags:
            msg += f"  • {tag}\n"
    if price_action is not None:
        msg += f"Price Action: <b>{price_action.label}</b>\n"
        for tag in price_action.tags:
            msg += f"  • {tag}\n"
    return msg
