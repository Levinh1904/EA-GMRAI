"""Telegram must only render trade_ens signals, never regime labels."""
from app.services.telegram import render_signal_message


def test_telegram_message_is_trade_signal_only():
    text = render_signal_message(
        signal="LONG",
        previous_signal="SIDEWAYS",
        bar_ts="2026-11-18T02:00:00+00:00",
        price=4000.0,
        p_long=0.91,
        p_short=0.08,
        threshold=0.82,
        stale=False,
        local_offset_hours=7,
    )
    assert "TRADE_ENS" in text
    assert "LONG" in text
    assert "TREND_UP" not in text
    assert "TREND_DOWN" not in text
    assert "SIDEWAYS" not in text
    assert "p(LONG)" in text


def test_unknown_signal_is_folded_to_no_trade():
    text = render_signal_message(
        signal="TREND_UP",
        previous_signal="TREND_DOWN",
        bar_ts=None,
        price=None,
    )
    assert "NO_TRADE" in text
    assert "TREND_UP" not in text
    assert "TREND_DOWN" not in text
