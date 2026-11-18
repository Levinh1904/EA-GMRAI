"""Telegram notifications with dedupe and a full delivery log.

Rules (all enforced in one place so behaviour cannot drift):
  * Every attempt is written to `telegram_messages` — sent, skipped or failed.
  * `dedupe_key` is UNIQUE: the same signal for the same bar can never be sent
    twice, no matter how often the scheduler or the UI triggers a check.
  * A repeated direction is NOT re-sent: if the previous alert was TREND_DOWN and
    the new one is also TREND_DOWN, the message is recorded as `skipped` with
    reason `duplicate_direction`. A change of direction sends again.
  * Notification failures never propagate into inference or ingestion.

Settings: GMRAI_TELEGRAM_BOT_TOKEN, GMRAI_TELEGRAM_CHAT_ID, GMRAI_TELEGRAM_ENABLED.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import MarketCandle, ModelPrediction, TelegramMessage
from app.timeutil import ensure_utc, utcnow

logger = logging.getLogger("gmrai.telegram")

API_BASE = "https://api.telegram.org"
TIMEOUT = 10.0

REGIME_LABELS = {
    "TREND_UP": "XU HƯỚNG TĂNG",
    "TREND_DOWN": "XU HƯỚNG GIẢM",
    "SIDEWAYS": "ĐI NGANG",
    "EARLY_TREND_UP": "TĂNG SỚM (chưa xác nhận)",
    "EARLY_TREND_DOWN": "GIẢM SỚM (chưa xác nhận)",
    "TRANSITION": "CHUYỂN TIẾP",
    "HIGH_VOLATILITY": "BIẾN ĐỘNG CAO",
    "UNKNOWN": "KHÔNG XÁC ĐỊNH",
}


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------

def is_configured() -> bool:
    return bool(settings.telegram_bot_token and settings.telegram_chat_id)


def _post(text: str, chat_id: str | None = None) -> tuple[bool, int | None, str | None]:
    """Send via Bot API. Returns (ok, message_id, error) — never raises."""
    if not is_configured():
        return False, None, "telegram_not_configured"
    payload = {
        "chat_id": chat_id or settings.telegram_chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        resp = httpx.post(
            f"{API_BASE}/bot{settings.telegram_bot_token}/sendMessage",
            json=payload,
            timeout=TIMEOUT,
        )
        body = resp.json() if resp.content else {}
        if resp.status_code == 200 and body.get("ok"):
            return True, int(body["result"]["message_id"]), None
        return False, None, f"telegram_http_{resp.status_code}: {str(body)[:200]}"
    except Exception as e:  # network/timeout/parse — never bubble up
        logger.warning("Telegram send failed: %s", e)
        return False, None, f"{type(e).__name__}: {e}"[:500]


# ---------------------------------------------------------------------------
# Message rendering
# ---------------------------------------------------------------------------

def _fmt_price(v: float | None) -> str:
    return "—" if v is None else f"{v:,.2f}"


def _fmt_ts(dt: datetime | str | None) -> str:
    """Render a timestamp as UTC. Accepts datetime or an ISO string."""
    if dt is None:
        return "—"
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except ValueError:
            return dt
    return ensure_utc(dt).strftime("%Y-%m-%d %H:%M UTC")


def _fmt_ts_local(dt: datetime | str | None, offset_hours: int) -> str:
    """Render the same instant in the recipient's local time.

    Telegram shows message times in the phone's timezone, while every timestamp
    in this system is UTC. Sending both removes the "why does Telegram say 00:10
    when the web says 17:00" confusion — they are the same moment.
    """
    if dt is None:
        return ""
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except ValueError:
            return ""
    local = ensure_utc(dt) + timedelta(hours=offset_hours)
    sign = "+" if offset_hours >= 0 else "-"
    return f"{local.strftime('%H:%M')} (GMT{sign}{abs(offset_hours)})"


def _bar_close(bar_open: datetime | str | None, period_seconds: int = 900) -> datetime | str | None:
    """Convert a bar OPEN timestamp to its CLOSE timestamp.

    `model_predictions.ts` stores the bar's open time (that is the candle's
    identity), but an alert describes a *closed* candle. The old message labelled
    the open time as "Nến đóng", so every alert was one M15 bar (15 min) off from
    what it claimed — on top of the UTC/local difference.
    """
    if bar_open is None:
        return None
    if isinstance(bar_open, str):
        try:
            dt = datetime.fromisoformat(bar_open.replace("Z", "+00:00"))
        except ValueError:
            return bar_open
        return (ensure_utc(dt) + timedelta(seconds=period_seconds)).isoformat()
    return ensure_utc(bar_open) + timedelta(seconds=period_seconds)


def render_signal_message(
    *,
    signal: str,
    previous_signal: str | None,
    bar_ts: datetime | None,
    price: float | None,
    confidence: float | None,
    forecast: dict | None = None,
    changed: bool = True,
    local_offset_hours: int | None = None,
) -> str:
    """Build the alert body. Kept separate so it is trivially testable."""
    label = REGIME_LABELS.get(signal, signal)
    lines = [
        f"<b>GMRAI · XAUUSD M15</b>",
        f"Tín hiệu: <b>{label}</b> ({signal})",
    ]
    if changed and previous_signal:
        prev = REGIME_LABELS.get(previous_signal, previous_signal)
        lines.append(f"Trước đó: {prev} ({previous_signal})")
    bar_local = (
        _fmt_ts_local(_bar_close(bar_ts), local_offset_hours)
        if local_offset_hours is not None
        else ""
    )
    lines.append(
        f"Nến đóng: {_fmt_ts(_bar_close(bar_ts))}"
        + (f"  ·  {bar_local} giờ máy" if bar_local else "")
    )
    lines.append(f"Giá đóng: {_fmt_price(price)}")
    if confidence is not None:
        lines.append(f"Độ tin cậy: {confidence * 100:.1f}%")
    if forecast:
        d = forecast.get("direction")
        p_up = forecast.get("probability_up")
        target = forecast.get("target_ts")
        arrow = {"UP": "↑ tăng", "DOWN": "↓ giảm", "FLAT": "→ đi ngang"}.get(d, d)
        if p_up is not None:
            lines.append(
                f"Nến kế tiếp (dự đoán): <b>{arrow}</b> · P(up)={p_up * 100:.1f}%"
            )
        else:
            lines.append(f"Nến kế tiếp (dự đoán): <b>{arrow}</b>")
        target_local = (
            _fmt_ts_local(target, local_offset_hours) if local_offset_hours is not None else ""
        )
        lines.append(
            f"  → nến kế tiếp mở lúc: {_fmt_ts(target)}"
            + (f"  ·  {target_local}" if target_local else "")
        )
    lines.append("")
    lines.append(
        "<i>Công cụ nghiên cứu — không phải lời khuyên đầu tư, không gửi lệnh giao dịch.</i>"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Logging + dedupe
# ---------------------------------------------------------------------------

def _existing(db: Session, dedupe_key: str) -> TelegramMessage | None:
    return (
        db.query(TelegramMessage)
        .filter(TelegramMessage.dedupe_key == dedupe_key)
        .first()
    )


def _last_alert(db: Session, symbol: str) -> TelegramMessage | None:
    return (
        db.query(TelegramMessage)
        .filter(
            TelegramMessage.kind == "signal",
            TelegramMessage.symbol == symbol,
            TelegramMessage.status == "sent",
        )
        .order_by(TelegramMessage.id.desc())
        .first()
    )


def _record(
    db: Session,
    *,
    dedupe_key: str,
    kind: str,
    status: str,
    text: str,
    symbol: str = "XAUUSD",
    signal: str | None = None,
    previous_signal: str | None = None,
    bar_ts: datetime | None = None,
    price: float | None = None,
    confidence: float | None = None,
    reason: str | None = None,
    message_id: int | None = None,
    error: str | None = None,
) -> TelegramMessage:
    msg = TelegramMessage(
        dedupe_key=dedupe_key,
        kind=kind,
        status=status,
        symbol=symbol,
        signal=signal,
        previous_signal=previous_signal,
        bar_ts=bar_ts,
        price=price,
        confidence=confidence,
        text=text[:4000],
        reason=reason,
        chat_id=settings.telegram_chat_id or None,
        message_id=message_id,
        error=error,
        sent_at=utcnow() if status == "sent" else None,
    )
    db.add(msg)
    try:
        db.commit()
    except IntegrityError:
        # Another worker recorded this exact key first — that IS the dedupe.
        db.rollback()
        found = _existing(db, dedupe_key)
        if found is not None:
            return found
        raise
    return msg


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def notify_signal(
    db: Session,
    symbol: str = "XAUUSD",
    include_forecast: bool = True,
    alert_max_age_seconds: int | None = None,
) -> dict:
    """Send an alert for the latest closed-bar regime, skipping repeats.

    Returns a dict describing what happened (`sent`, `skipped`, `failed`,
    `reason`) so callers (worker, API, UI) can display it.
    """
    from app.services.forecast import forecast_next_bar

    pred = (
        db.query(ModelPrediction)
        .filter(ModelPrediction.symbol == symbol)
        .order_by(ModelPrediction.ts.desc())
        .first()
    )
    if pred is None:
        return {"status": "skipped", "reason": "no_prediction"}

    bar_ts = ensure_utc(pred.ts)
    signal = pred.regime
    dedupe_key = f"signal:{symbol}:{bar_ts.isoformat()}:{signal}"

    if _existing(db, dedupe_key) is not None:
        found = _existing(db, dedupe_key)
        return {
            "status": "skipped",
            "reason": "already_logged_for_bar",
            "id": found.id if found is not None else None,
        }

    last = _last_alert(db, symbol)

    # "Previous" must mean the previous BAR, not the previous MESSAGE.
    #
    # These diverge whenever an alert was skipped (dedupe/cooldown) or the app
    # was down: the last message could be hours old and about a totally
    # different stretch of market. Labelling a fresh TREND_DOWN as
    # "Trước đó: ĐI NGANG" while the preceding eight bars were also TREND_DOWN
    # is simply false, and it is exactly what made the alert look tampered with.
    prev_pred = (
        db.query(ModelPrediction)
        .filter(
            ModelPrediction.symbol == symbol,
            ModelPrediction.timeframe == pred.timeframe,
            ModelPrediction.ts < bar_ts,
        )
        .order_by(ModelPrediction.ts.desc())
        .first()
    )
    previous_signal = prev_pred.regime if prev_pred is not None else (last.signal if last else None)

    # Never alert on a bar that is no longer "the one that just closed".
    #
    # Backfill can create a prediction for a candle that closed hours ago; the
    # scheduler would then treat it as breaking news. An alert is only useful
    # while the next bar is still forming.
    if alert_max_age_seconds is None:
        alert_max_age_seconds = settings.telegram_max_bar_age_seconds
    bar_age = (utcnow() - bar_ts).total_seconds()
    too_old = alert_max_age_seconds > 0 and bar_age > alert_max_age_seconds

    bar = (
        db.query(MarketCandle)
        .filter(
            MarketCandle.symbol == symbol,
            MarketCandle.timeframe == "M15",
            MarketCandle.ts == bar_ts,
        )
        .order_by(MarketCandle.id.desc())
        .first()
    )
    price = float(bar.close) if bar else None

    forecast = None
    if include_forecast:
        try:
            forecast = forecast_next_bar(db, symbol)
        except Exception:
            logger.debug("forecast unavailable for telegram message", exc_info=True)

    # Repeating the SAME regime is not news — stay quiet. This applies to every
    # regime, not just trends: an unchanged SIDEWAYS was re-sent on every scan
    # (every 5-10 minutes) because the old check only covered TREND_UP/DOWN.
    duplicate = previous_signal is not None and previous_signal == signal

    # Hard cap: at most one alert per `telegram_min_bar_seconds` (default 900s =
    # the M15 candle the models trade on). This is the real throttle, so the
    # scheduler can poll often without spamming the chat.
    within_cooldown = False
    cooldown_left = None
    if last is not None and last.sent_at is not None:
        elapsed = (utcnow() - ensure_utc(last.sent_at)).total_seconds()
        if elapsed < settings.telegram_min_bar_seconds:
            within_cooldown = True
            cooldown_left = int(settings.telegram_min_bar_seconds - elapsed)

    text = render_signal_message(
        signal=signal,
        previous_signal=previous_signal,
        bar_ts=bar_ts,
        price=price,
        confidence=float(pred.confidence or 0.0),
        forecast=forecast,
        changed=not duplicate,
        local_offset_hours=settings.telegram_local_offset_hours,
    )

    for blocked, reason in (
        (too_old, f"bar_too_old_{int(bar_age)}s"),
        (within_cooldown, f"cooldown_{cooldown_left}s" if cooldown_left else "cooldown"),
        (duplicate, "duplicate_regime"),
    ):
        if blocked:
            msg = _record(
                db,
                dedupe_key=dedupe_key,
                kind="signal",
                status="skipped",
                text=text,
                symbol=symbol,
                signal=signal,
                previous_signal=previous_signal,
                bar_ts=bar_ts,
                price=price,
                confidence=float(pred.confidence or 0.0),
                reason=reason,
            )
            return {"status": "skipped", "reason": reason, "id": msg.id}

    if not settings.telegram_enabled or not is_configured():
        msg = _record(
            db,
            dedupe_key=dedupe_key,
            kind="signal",
            status="skipped",
            text=text,
            symbol=symbol,
            signal=signal,
            previous_signal=previous_signal,
            bar_ts=bar_ts,
            price=price,
            confidence=float(pred.confidence or 0.0),
            reason="telegram_disabled" if not settings.telegram_enabled else "not_configured",
        )
        return {"status": "skipped", "reason": "telegram_disabled", "id": msg.id}

    ok, message_id, error = _post(text)
    msg = _record(
        db,
        dedupe_key=dedupe_key,
        kind="signal",
        status="sent" if ok else "failed",
        text=text,
        symbol=symbol,
        signal=signal,
        previous_signal=previous_signal,
        bar_ts=bar_ts,
        price=price,
        confidence=float(pred.confidence or 0.0),
        reason="ok" if ok else None,
        message_id=message_id,
        error=error,
    )
    return {
        "status": "sent" if ok else "failed",
        "id": msg.id,
        "message_id": message_id,
        "error": error,
    }


def send_test_message(db: Session) -> dict:
    """Admin-only connectivity check; also logged."""
    text = (
        "<b>GMRAI · kiểm tra Telegram</b>\n"
        f"Thời điểm: {_fmt_ts(utcnow())}\n"
        "Nếu bạn thấy tin này, cấu hình bot đã đúng."
    )
    key = f"test:{utcnow().isoformat()}"
    ok, message_id, error = _post(text)
    msg = _record(
        db,
        dedupe_key=key,
        kind="test",
        status="sent" if ok else "failed",
        text=text,
        reason="ok" if ok else None,
        message_id=message_id,
        error=error,
    )
    return {"status": "sent" if ok else "failed", "id": msg.id, "error": error}


def telegram_status(db: Session) -> dict:
    """Configuration + delivery health, from the log itself."""
    total = db.query(TelegramMessage).count()
    sent = db.query(TelegramMessage).filter(TelegramMessage.status == "sent").count()
    skipped = db.query(TelegramMessage).filter(TelegramMessage.status == "skipped").count()
    failed = db.query(TelegramMessage).filter(TelegramMessage.status == "failed").count()
    last = (
        db.query(TelegramMessage)
        .order_by(TelegramMessage.id.desc())
        .first()
    )
    # Cooldown: at most one alert per `telegram_min_bar_seconds`.
    last_signal = (
        db.query(TelegramMessage)
        .filter(TelegramMessage.kind == "signal", TelegramMessage.status == "sent")
        .order_by(TelegramMessage.id.desc())
        .first()
    )
    cooldown_left = None
    if last_signal is not None and last_signal.sent_at is not None:
        elapsed = (utcnow() - ensure_utc(last_signal.sent_at)).total_seconds()
        cooldown_left = max(0, int(settings.telegram_min_bar_seconds - elapsed))

    # How many recent signal rows were suppressed — makes the anti-spam visible.
    recent_signal = (
        db.query(TelegramMessage)
        .filter(TelegramMessage.kind == "signal")
        .order_by(TelegramMessage.id.desc())
        .limit(50)
        .all()
    )
    suppressed = sum(1 for r in recent_signal if r.status == "skipped" and r.reason)

    return {
        "enabled": settings.telegram_enabled,
        "configured": is_configured(),
        "chat_id": (settings.telegram_chat_id[:4] + "***") if settings.telegram_chat_id else None,
        "counts": {"total": total, "sent": sent, "skipped": skipped, "failed": failed},
        "throttle": {
            "check_interval_seconds": settings.telegram_interval_seconds,
            "min_bar_seconds": settings.telegram_min_bar_seconds,
            "min_bar_minutes": settings.telegram_min_bar_seconds // 60,
            "cooldown_left_seconds": cooldown_left,
            "signals_suppressed_recent": suppressed,
            "note": (
                "Tối đa 1 tin tín hiệu mỗi "
                f"{settings.telegram_min_bar_seconds // 60} phút (khớp nến M15 trên MT5). "
                "Cùng một chế độ lặp lại sẽ không gửi lại."
            ),
        },
        "last": None
        if last is None
        else {
            "id": last.id,
            "status": last.status,
            "signal": last.signal,
            "reason": last.reason,
            "created_at": ensure_utc(last.created_at).isoformat(),
            "error": last.error,
        },
    }


def list_messages(
    db: Session,
    limit: int = 100,
    offset: int = 0,
    status: str | None = None,
    kind: str | None = None,
) -> dict:
    q = db.query(TelegramMessage)
    if status:
        q = q.filter(TelegramMessage.status == status)
    if kind:
        q = q.filter(TelegramMessage.kind == kind)
    total = q.count()
    rows = q.order_by(TelegramMessage.id.desc()).offset(offset).limit(limit).all()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "messages": [
            {
                "id": r.id,
                "kind": r.kind,
                "status": r.status,
                "symbol": r.symbol,
                "signal": r.signal,
                "previous_signal": r.previous_signal,
                "bar_ts": ensure_utc(r.bar_ts).isoformat() if r.bar_ts else None,
                "price": r.price,
                "confidence": r.confidence,
                "text": r.text,
                "reason": r.reason,
                "message_id": r.message_id,
                "error": r.error,
                "created_at": ensure_utc(r.created_at).isoformat(),
                "sent_at": ensure_utc(r.sent_at).isoformat() if r.sent_at else None,
            }
            for r in rows
        ],
    }
