"""Next-bar forecast + Telegram notifications.

Locks the guarantees that matter operationally:
  * one forecast per closed bar, never overwritten (accuracy stays honest)
  * dedupe: the same signal for the same bar is sent at most once
  * a repeated direction is skipped, a changed direction sends again
  * notification failures never raise into callers
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.config import settings
from app.models import BarForecast, MarketCandle, ModelPrediction, TelegramMessage
from app.services import telegram as tg
from app.services.forecast import (
    _direction_from_probability,
    forecast_stats,
    score_pending_forecasts,
)
from app.services.telegram import (
    list_messages,
    render_signal_message,
    telegram_status,
)


def _ts(y=None, m=None, d=None, h=None, mi=None):
    """A recent M15 bar open time by default.

    Tests used to pin 2026-11-13, which breaks now that a stale bar is
    deliberately refused (an alert must describe a bar that just closed).
    Passing explicit y/m/d/h/mi still means UTC on that date.
    """
    if y is None:
        from app.timeutil import utcnow

        now = utcnow() - timedelta(minutes=10)
        return now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def _recent(minutes_ago: int = 10):
    from app.timeutil import utcnow

    now = utcnow() - timedelta(minutes=minutes_ago)
    return now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)


def _add_candle(s, ts, o, c, source="ftmo_mt5"):
    s.add(
        MarketCandle(
            symbol="XAUUSD", timeframe="M15", ts=ts, open=o,
            high=max(o, c) + 1, low=min(o, c) - 1, close=c,
            tick_volume=100, source=source,
        )
    )


def _add_prediction(s, ts, regime, conf=0.9):
    s.add(
        ModelPrediction(
            model_version_id=1, symbol="XAUUSD", timeframe="M15", ts=ts,
            regime=regime, confidence=conf,
        )
    )


# ---------------------------------------------------------------------------
# Direction mapping
# ---------------------------------------------------------------------------

def test_direction_mapping_has_flat_band():
    assert _direction_from_probability(0.80)[0] == "UP"
    assert _direction_from_probability(0.20)[0] == "DOWN"
    assert _direction_from_probability(0.50)[0] == "FLAT"
    assert _direction_from_probability(0.52)[0] == "FLAT"
    # Confidence is the distance from a coin flip, symmetrically.
    assert _direction_from_probability(0.80)[1] == pytest.approx(0.80)
    assert _direction_from_probability(0.20)[1] == pytest.approx(0.80)


# ---------------------------------------------------------------------------
# Forecast scoring
# ---------------------------------------------------------------------------

def test_forecast_scored_once_target_bar_exists(db):
    from app.db import session

    with session() as s:
        bar = _ts(h=7, mi=45)
        _add_candle(s, bar, 3900, 3898)
        _add_candle(s, bar + timedelta(minutes=15), 3898, 3890)  # closes DOWN
        s.add(
            BarForecast(
                symbol="XAUUSD", timeframe="M15", ts=bar,
                target_ts=bar + timedelta(minutes=15),
                direction="DOWN", probability_up=0.25, confidence=0.75,
                method="test",
            )
        )
        s.commit()

        out = score_pending_forecasts(s, "XAUUSD")
        assert out["scored"] == 1 and out["correct"] == 1

        fc = s.query(BarForecast).first()
        assert fc.actual_direction == "DOWN"
        assert fc.correct is True
        assert fc.scored_at is not None


def test_forecast_wrong_call_is_recorded_as_wrong(db):
    from app.db import session

    with session() as s:
        bar = _ts(h=7, mi=45)
        _add_candle(s, bar, 3890, 3895)
        _add_candle(s, bar + timedelta(minutes=15), 3895, 3910)  # closes UP
        s.add(
            BarForecast(
                symbol="XAUUSD", timeframe="M15", ts=bar,
                target_ts=bar + timedelta(minutes=15),
                direction="DOWN", probability_up=0.20, confidence=0.80,
                method="test",
            )
        )
        s.commit()
        score_pending_forecasts(s, "XAUUSD")
        fc = s.query(BarForecast).first()
        assert fc.correct is False


def test_forecast_not_scored_before_target_closes(db):
    from app.db import session

    with session() as s:
        bar = _ts()
        _add_candle(s, bar, 3900, 3898)
        s.add(
            BarForecast(
                symbol="XAUUSD", timeframe="M15", ts=bar,
                target_ts=bar + timedelta(minutes=15),
                direction="UP", probability_up=0.7, confidence=0.7, method="test",
            )
        )
        s.commit()
        out = score_pending_forecasts(s, "XAUUSD")
        assert out["scored"] == 0
        assert s.query(BarForecast).first().correct is None


def test_forecast_stats_ignores_unscored(db):
    from app.db import session

    with session() as s:
        for i, (correct, direction) in enumerate(
            [(True, "UP"), (True, "DOWN"), (False, "UP"), (None, "UP")]
        ):
            s.add(
                BarForecast(
                    symbol="XAUUSD", timeframe="M15",
                    ts=_ts() + timedelta(minutes=15 * i),
                    target_ts=_ts() + timedelta(minutes=15 * (i + 1)),
                    direction=direction, probability_up=0.7, confidence=0.7,
                    method="test", correct=correct, scored_at=None if correct is None else _ts(),
                )
            )
        s.commit()
        stats = forecast_stats(s, "XAUUSD")
        assert stats["scored"] == 3
        assert stats["accuracy"] == pytest.approx(2 / 3, abs=1e-3)
        assert stats["by_direction"]["UP"]["n"] == 2
        assert stats["by_direction"]["UP"]["accuracy"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Message rendering
# ---------------------------------------------------------------------------

def test_render_includes_regime_price_and_forecast():
    text = render_signal_message(
        signal="TREND_DOWN",
        previous_signal="SIDEWAYS",
        bar_ts=_ts(),
        price=3918.06,
        confidence=0.92,
        forecast={"direction": "DOWN", "probability_up": 0.31,
                  "target_ts": "2026-11-13T08:00:00+00:00"},
    )
    assert "XU HƯỚNG GIẢM" in text
    assert "TREND_DOWN" in text
    assert "3,918.06" in text
    assert "92.0%" in text
    assert "Nến kế tiếp" in text
    assert "31.0%" in text
    assert "UTC" in text


def test_render_omits_previous_when_unchanged():
    text = render_signal_message(
        signal="TREND_DOWN", previous_signal="TREND_DOWN",
        bar_ts=_ts(), price=3900.0, confidence=0.8, changed=False,
    )
    assert "Trước đó" not in text


def test_render_handles_missing_price_and_forecast():
    text = render_signal_message(
        signal="SIDEWAYS", previous_signal=None, bar_ts=None,
        price=None, confidence=None, forecast=None,
    )
    assert "ĐI NGANG" in text
    assert "—" in text


# ---------------------------------------------------------------------------
# Dedupe + logging
# ---------------------------------------------------------------------------

def _setup_signal(db, regime="TREND_DOWN", bar=None):
    from app.db import session

    bar = bar or _ts()
    with session() as s:
        _add_candle(s, bar, 3900, 3890)
        _add_prediction(s, bar, regime)
        s.commit()
    return bar


def test_notify_logs_skipped_when_disabled(db, monkeypatch):
    monkeypatch.setattr(settings, "telegram_enabled", False)
    _setup_signal(db)
    from app.db import session

    with session() as s:
        out = tg.notify_signal(s, "XAUUSD", include_forecast=False)
        assert out["status"] == "skipped"
        msg = s.query(TelegramMessage).one()
        assert msg.status == "skipped"
        assert msg.reason == "telegram_disabled"
        assert msg.signal == "TREND_DOWN"


def test_notify_is_idempotent_for_same_bar(db, monkeypatch):
    monkeypatch.setattr(settings, "telegram_enabled", False)
    _setup_signal(db)
    from app.db import session

    with session() as s:
        first = tg.notify_signal(s, "XAUUSD", include_forecast=False)
        second = tg.notify_signal(s, "XAUUSD", include_forecast=False)
        assert first["id"] == second["id"]
        assert second["reason"] == "already_logged_for_bar"
        assert s.query(TelegramMessage).count() == 1


def test_repeated_direction_is_skipped(db, monkeypatch):
    """Same direction on the next bar must NOT be sent again."""
    monkeypatch.setattr(settings, "telegram_enabled", True)
    monkeypatch.setattr(settings, "telegram_bot_token", "t")
    monkeypatch.setattr(settings, "telegram_chat_id", "c")
    monkeypatch.setattr(settings, "telegram_min_bar_seconds", 0)  # cooldown tested separately
    sent: list[str] = []
    monkeypatch.setattr(tg, "_post", lambda text, chat_id=None: (sent.append(text) or (True, 111, None)))

    from app.db import session

    bar1 = _ts(h=7, mi=45)
    _setup_signal(db, "TREND_DOWN", bar1)

    with session() as s:
        first = tg.notify_signal(s, "XAUUSD", include_forecast=False)
        assert first["status"] == "sent" and len(sent) == 1

    # A NEW bar arrives with the same direction -> skipped, no new send.
    bar2 = bar1 + timedelta(minutes=15)
    with session() as s:
        _add_candle(s, bar2, 3890, 3880)
        _add_prediction(s, bar2, "TREND_DOWN")
        s.commit()
    with session() as s:
        second = tg.notify_signal(s, "XAUUSD", include_forecast=False)
        assert second["status"] == "skipped"
        assert second["reason"] in ("duplicate_regime", "duplicate_direction")
        assert len(sent) == 1
        rows = s.query(TelegramMessage).order_by(TelegramMessage.id).all()
        assert [r.status for r in rows] == ["sent", "skipped"]


def test_changed_direction_sends_again(db, monkeypatch):
    monkeypatch.setattr(settings, "telegram_enabled", True)
    monkeypatch.setattr(settings, "telegram_bot_token", "t")
    monkeypatch.setattr(settings, "telegram_chat_id", "c")
    monkeypatch.setattr(settings, "telegram_min_bar_seconds", 0)  # cooldown tested separately
    sent: list[str] = []
    monkeypatch.setattr(tg, "_post", lambda text, chat_id=None: (sent.append(text) or (True, 222, None)))

    from app.db import session

    bar1 = _ts(h=7, mi=45)
    _setup_signal(db, "TREND_DOWN", bar1)

    with session() as s:
        first = tg.notify_signal(s, "XAUUSD", include_forecast=False)
        assert first["status"] == "sent"

    # New bar, direction flipped -> must send again.
    bar2 = bar1 + timedelta(minutes=15)
    with session() as s:
        _add_candle(s, bar2, 3880, 3895)
        _add_prediction(s, bar2, "TREND_UP")
        s.commit()
    with session() as s:
        second = tg.notify_signal(s, "XAUUSD", include_forecast=False)
        assert second["status"] == "sent"
        assert len(sent) == 2
        rows = s.query(TelegramMessage).order_by(TelegramMessage.id).all()
        assert rows[-1].previous_signal == "TREND_DOWN"
        assert rows[-1].signal == "TREND_UP"


def test_transport_failure_is_logged_not_raised(db, monkeypatch):
    monkeypatch.setattr(settings, "telegram_enabled", True)
    monkeypatch.setattr(settings, "telegram_bot_token", "t")
    monkeypatch.setattr(settings, "telegram_chat_id", "c")
    monkeypatch.setattr(tg, "_post", lambda text, chat_id=None: (False, None, "boom"))

    _setup_signal(db)
    from app.db import session

    with session() as s:
        out = tg.notify_signal(s, "XAUUSD", include_forecast=False)
        assert out["status"] == "failed"
        msg = s.query(TelegramMessage).one()
        assert msg.status == "failed"
        assert msg.error == "boom"


def test_notify_without_prediction_is_skipped(db):
    from app.db import session

    with session() as s:
        out = tg.notify_signal(s, "XAUUSD", include_forecast=False)
        assert out["status"] == "skipped"
        assert out["reason"] == "no_prediction"
        assert s.query(TelegramMessage).count() == 0


# ---------------------------------------------------------------------------
# Status + history API surface
# ---------------------------------------------------------------------------

def test_status_reports_counts_from_log(db):
    from app.db import session

    with session() as s:
        s.add(TelegramMessage(dedupe_key="a", kind="signal", status="sent", text="x", signal="TREND_UP"))
        s.add(TelegramMessage(dedupe_key="b", kind="signal", status="skipped", text="y", reason="dup"))
        s.add(TelegramMessage(dedupe_key="c", kind="test", status="failed", text="z", error="e"))
        s.commit()
        st = telegram_status(s)
        assert st["counts"] == {"total": 3, "sent": 1, "skipped": 1, "failed": 1}
        assert st["last"]["status"] == "failed"


def test_message_history_filters(db):
    from app.db import session

    with session() as s:
        for i in range(5):
            s.add(TelegramMessage(
                dedupe_key=f"k{i}", kind="signal",
                status="sent" if i % 2 == 0 else "skipped",
                text=f"msg {i}", signal="TREND_UP",
            ))
        s.commit()
        allm = list_messages(s, limit=10)
        assert allm["total"] == 5 and len(allm["messages"]) == 5
        # newest first
        assert allm["messages"][0]["text"] == "msg 4"

        sent = list_messages(s, status="sent")
        assert sent["total"] == 3

        page = list_messages(s, limit=2, offset=0)
        assert len(page["messages"]) == 2


# ---------------------------------------------------------------------------
# Spam protection — the bug that shipped: an unchanged SIDEWAYS was re-sent on
# every scan (every 5-10 min) because dedupe only covered TREND_UP/DOWN.
# ---------------------------------------------------------------------------

def test_unchanged_sideways_is_not_resent(db, monkeypatch):
    """SIDEWAYS must dedupe exactly like a trend does."""
    monkeypatch.setattr(settings, "telegram_enabled", True)
    monkeypatch.setattr(settings, "telegram_bot_token", "t")
    monkeypatch.setattr(settings, "telegram_chat_id", "c")
    monkeypatch.setattr(settings, "telegram_min_bar_seconds", 0)
    sent: list[str] = []
    monkeypatch.setattr(tg, "_post", lambda text, chat_id=None: (sent.append(text) or (True, 1, None)))

    from app.db import session

    bar1 = _ts(h=7, mi=45)
    _setup_signal(db, "SIDEWAYS", bar1)
    with session() as s:
        assert tg.notify_signal(s, "XAUUSD", include_forecast=False)["status"] == "sent"
    assert len(sent) == 1

    # New bar, same SIDEWAYS -> must stay quiet.
    bar2 = bar1 + timedelta(minutes=15)
    with session() as s:
        _add_candle(s, bar2, 3900, 3901)
        _add_prediction(s, bar2, "SIDEWAYS")
        s.commit()
    with session() as s:
        out = tg.notify_signal(s, "XAUUSD", include_forecast=False)
    assert out["status"] == "skipped"
    assert out["reason"] == "duplicate_regime"
    assert len(sent) == 1, "unchanged SIDEWAYS must not be re-sent"


def test_cooldown_blocks_second_message_within_bar_window(db, monkeypatch):
    """At most one alert per M15 bar (900s), even if the regime changes."""
    monkeypatch.setattr(settings, "telegram_enabled", True)
    monkeypatch.setattr(settings, "telegram_bot_token", "t")
    monkeypatch.setattr(settings, "telegram_chat_id", "c")
    monkeypatch.setattr(settings, "telegram_min_bar_seconds", 900)
    sent: list[str] = []
    monkeypatch.setattr(tg, "_post", lambda text, chat_id=None: (sent.append(text) or (True, 1, None)))

    from app.db import session

    bar1 = _ts(h=7, mi=45)
    _setup_signal(db, "TREND_DOWN", bar1)
    with session() as s:
        assert tg.notify_signal(s, "XAUUSD", include_forecast=False)["status"] == "sent"

    # Regime flips immediately (next bar) -> still inside the 900s window.
    bar2 = bar1 + timedelta(minutes=15)
    with session() as s:
        _add_candle(s, bar2, 3890, 3895)
        _add_prediction(s, bar2, "TREND_UP")
        s.commit()
    with session() as s:
        out = tg.notify_signal(s, "XAUUSD", include_forecast=False)
    assert out["status"] == "skipped"
    assert out["reason"].startswith("cooldown")
    assert len(sent) == 1


def test_cooldown_expires_and_sends_again(db, monkeypatch):
    monkeypatch.setattr(settings, "telegram_enabled", True)
    monkeypatch.setattr(settings, "telegram_bot_token", "t")
    monkeypatch.setattr(settings, "telegram_chat_id", "c")
    monkeypatch.setattr(settings, "telegram_min_bar_seconds", 0)
    sent: list[str] = []
    monkeypatch.setattr(tg, "_post", lambda text, chat_id=None: (sent.append(text) or (True, 1, None)))

    from app.db import session

    bar1 = _ts(h=7, mi=45)
    _setup_signal(db, "TREND_DOWN", bar1)
    with session() as s:
        assert tg.notify_signal(s, "XAUUSD", include_forecast=False)["status"] == "sent"

    bar2 = bar1 + timedelta(minutes=15)
    with session() as s:
        _add_candle(s, bar2, 3890, 3895)
        _add_prediction(s, bar2, "TREND_UP")
        s.commit()
    with session() as s:
        out = tg.notify_signal(s, "XAUUSD", include_forecast=False)
    assert out["status"] == "sent"
    assert len(sent) == 2


def test_min_bar_seconds_defaults_to_m15(monkeypatch):
    """The throttle must match the decision timeframe the models use."""
    from app.config import Settings

    s = Settings(_env_file=None)
    assert s.telegram_min_bar_seconds == 900  # 15 minutes


# ---------------------------------------------------------------------------
# Timezone clarity: Telegram shows phone-local time, the web shows UTC.
# Both must appear so the two views are provably the same instant.
# ---------------------------------------------------------------------------

def test_message_shows_both_utc_and_local_time():
    text = render_signal_message(
        signal="SIDEWAYS",
        previous_signal="SIDEWAYS",
        bar_ts=datetime(2026, 11, 13, 17, 15, tzinfo=timezone.utc),
        price=3877.51,
        confidence=0.69,
        forecast={
            "direction": "FLAT",
            "probability_up": 0.522,
            "target_ts": "2026-11-13T17:30:00+00:00",
        },
        local_offset_hours=7,
    )
    # The alert describes a CLOSED candle: open 17:15 -> close 17:30.
    assert "2026-11-13 17:30 UTC" in text
    # same instant in Vietnam time (UTC+7)
    assert "00:30 (GMT+7)" in text
    # forecast target is labelled separately so the two lines cannot be confused
    assert "nến kế tiếp mở lúc" in text


def test_message_omits_local_time_when_offset_absent():
    text = render_signal_message(
        signal="SIDEWAYS",
        previous_signal=None,
        bar_ts=datetime(2026, 11, 13, 17, 15, tzinfo=timezone.utc),
        price=3877.51,
        confidence=0.5,
    )
    # close time of the 17:15 bar
    assert "17:30 UTC" in text
    assert "GMT" not in text


def test_negative_offset_renders_correctly():
    text = render_signal_message(
        signal="TREND_UP",
        previous_signal=None,
        bar_ts=datetime(2026, 11, 13, 17, 15, tzinfo=timezone.utc),
        price=3900.0,
        confidence=0.7,
        local_offset_hours=-5,
    )
    assert "12:30 (GMT-5)" in text  # 17:30 UTC close time


def test_default_offset_is_vietnam():
    from app.config import Settings

    assert Settings(_env_file=None).telegram_local_offset_hours == 7


def test_message_reports_bar_close_not_open():
    """Regression: the alert used to label the bar's OPEN time as "Nến đóng",
    making every message appear one M15 bar (15 min) earlier than reality."""
    text = render_signal_message(
        signal="TREND_DOWN",
        previous_signal=None,
        bar_ts=datetime(2026, 11, 13, 17, 45, tzinfo=timezone.utc),  # OPEN
        price=3873.44,
        confidence=0.69,
        local_offset_hours=0,
    )
    assert "18:00 UTC" in text, "must show the close (17:45 + 15m), not the open"
    assert "17:45 UTC" not in text.split("Giá đóng")[0]


def test_bar_close_helper_handles_strings_and_none():
    from app.services.telegram import _bar_close

    assert _bar_close(None) is None
    out = _bar_close("2026-11-13T17:45:00+00:00")
    assert out.startswith("2026-11-13T18:00:00")
    assert _bar_close("not-a-date") == "not-a-date"


# ---------------------------------------------------------------------------
# Regressions from a real alert that looked tampered with:
#   "Tối nhận tin GIẢM nhưng giờ chỗ đó SIDEWAYS, có gian lận không?"
# Two separate defects produced it.
# ---------------------------------------------------------------------------

def test_previous_signal_is_previous_bar_not_previous_message(db, monkeypatch):
    """`Trước đó` must describe the preceding bar, not the last alert sent.

    The last message may be hours old and about a different stretch of market
    (it is skipped by dedupe/cooldown all the time), so using it produced
    "Trước đó: ĐI NGANG" while the eight preceding bars were TREND_DOWN.
    """
    monkeypatch.setattr(settings, "telegram_enabled", True)
    monkeypatch.setattr(settings, "telegram_bot_token", "t")
    monkeypatch.setattr(settings, "telegram_chat_id", "c")
    monkeypatch.setattr(settings, "telegram_min_bar_seconds", 0)
    monkeypatch.setattr(settings, "telegram_max_bar_age_seconds", 0)  # age tested separately
    sent: list[str] = []
    monkeypatch.setattr(tg, "_post", lambda text, chat_id=None: (sent.append(text) or (True, 1, None)))

    from app.db import session

    # Nine consecutive TREND_DOWN bars ending "now"; the OLDEST one is what the
    # message log will see as the last alert (it was sent for a SIDEWAYS bar
    # before this run).
    base = _recent(minutes_ago=15 * 10)
    _setup_signal(db, "SIDEWAYS", base)
    with session() as s:
        tg.notify_signal(s, "XAUUSD", include_forecast=False)  # message says SIDEWAYS

    for i in range(1, 10):
        ts = base + timedelta(minutes=15 * i)
        with session() as s:
            _add_candle(s, ts, 3900 - i, 3901 - i)
            _add_prediction(s, ts, "TREND_DOWN")
            s.commit()

    # Final bar flips direction so it is genuinely new (not a dedupe skip).
    flip = base + timedelta(minutes=15 * 10)
    with session() as s:
        _add_candle(s, flip, 3900, 3901)
        _add_prediction(s, flip, "TREND_UP")
        s.commit()

    with session() as s:
        out = tg.notify_signal(s, "XAUUSD", include_forecast=False)
    assert out["status"] == "sent"
    with session() as s:
        msg = s.query(tg.TelegramMessage).order_by(tg.TelegramMessage.id.desc()).first()

    # The bar before the alert is TREND_DOWN, so the alert must NOT claim
    # "Trước đó: ĐI NGANG" (which is what the stale message said).
    assert msg.previous_signal == "TREND_DOWN", (
        f"previous_signal should come from the previous BAR, got {msg.previous_signal!r}"
    )
    assert "ĐI NGANG" not in msg.text


def test_stale_bar_is_not_announced_as_news(db, monkeypatch):
    """A bar labelled hours late by backfill must not trigger a fresh alert."""
    monkeypatch.setattr(settings, "telegram_enabled", True)
    monkeypatch.setattr(settings, "telegram_bot_token", "t")
    monkeypatch.setattr(settings, "telegram_chat_id", "c")
    monkeypatch.setattr(settings, "telegram_min_bar_seconds", 0)
    monkeypatch.setattr(settings, "telegram_max_bar_age_seconds", 1800)
    sent: list[str] = []
    monkeypatch.setattr(tg, "_post", lambda text, chat_id=None: (sent.append(text) or (True, 1, None)))

    from app.db import session

    # Bar that closed 8 hours ago — exactly the backfill case that shipped.
    old = _ts(h=1, mi=0) if False else None
    from app.timeutil import utcnow

    old_ts = utcnow() - timedelta(hours=8)
    old_ts = old_ts.replace(minute=(old_ts.minute // 15) * 15, second=0, microsecond=0)
    with session() as s:
        _add_candle(s, old_ts, 3880, 3881)
        _add_prediction(s, old_ts, "TREND_DOWN")
        s.commit()

    with session() as s:
        out = tg.notify_signal(s, "XAUUSD", include_forecast=False)
    assert out["status"] == "skipped"
    assert out["reason"].startswith("bar_too_old")
    assert sent == [], "an 8-hour-old bar must never be sent as a new signal"


def test_fresh_bar_still_sends(db, monkeypatch):
    monkeypatch.setattr(settings, "telegram_enabled", True)
    monkeypatch.setattr(settings, "telegram_bot_token", "t")
    monkeypatch.setattr(settings, "telegram_chat_id", "c")
    monkeypatch.setattr(settings, "telegram_min_bar_seconds", 0)
    monkeypatch.setattr(settings, "telegram_max_bar_age_seconds", 1800)
    sent: list[str] = []
    monkeypatch.setattr(tg, "_post", lambda text, chat_id=None: (sent.append(text) or (True, 1, None)))

    from app.db import session
    from app.timeutil import utcnow

    fresh = utcnow() - timedelta(minutes=8)
    fresh = fresh.replace(minute=(fresh.minute // 15) * 15, second=0, microsecond=0)
    with session() as s:
        _add_candle(s, fresh, 3900, 3901)
        _add_prediction(s, fresh, "TREND_UP")
        s.commit()
    with session() as s:
        out = tg.notify_signal(s, "XAUUSD", include_forecast=False)
    assert out["status"] == "sent"
    assert len(sent) == 1


def test_max_bar_age_default_is_30_minutes():
    from app.config import Settings

    assert Settings(_env_file=None).telegram_max_bar_age_seconds == 1800
