"""Telegram delivery for trade_ens signals only.

Messages contain LONG / SHORT / NO_TRADE — never TREND_UP/SIDEWAYS/regime
labels. Every attempt is logged in `telegram_messages` and deduped per bar.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import TelegramMessage
from app.services.trade_signal import TradeSignalError, compute_latest_signal
from app.timeutil import ensure_utc, utcnow

logger = logging.getLogger("gmrai.telegram")
# Never let httpx log the Bot API URL (it contains the bot token).
logging.getLogger("httpx").setLevel(logging.WARNING)
API_BASE = "https://api.telegram.org"
TIMEOUT = 10.0
TRADE_SIGNALS = {"LONG", "SHORT", "NO_TRADE"}


def is_configured() -> bool:
    return bool(settings.telegram_bot_token and settings.telegram_chat_id)


def _post(text: str, chat_id: str | None = None) -> tuple[bool, int | None, str | None]:
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
    except Exception as e:
        logger.warning("Telegram send failed: %s", e)
        return False, None, f"{type(e).__name__}: {e}"[:500]


def _fmt_price(v: float | None) -> str:
    return "—" if v is None else f"{v:,.2f}"


def _fmt_ts(dt: datetime | str | None) -> str:
    if dt is None:
        return "—"
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except ValueError:
            return dt
    return ensure_utc(dt).strftime("%Y-%m-%d %H:%M UTC")


def _fmt_ts_local(dt: datetime | str | None, offset_hours: int) -> str:
    if not dt:
        return ""
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except ValueError:
            return ""
    local = ensure_utc(dt) + timedelta(hours=offset_hours)
    sign = "+" if offset_hours >= 0 else "-"
    return f"{local.strftime('%H:%M')} (GMT{sign}{abs(offset_hours)})"


def render_signal_message(
    *,
    signal: str,
    previous_signal: str | None = None,
    bar_ts: datetime | str | None = None,
    price: float | None = None,
    confidence: float | None = None,
    p_long: float | None = None,
    p_short: float | None = None,
    threshold: float | None = None,
    stale: bool = False,
    changed: bool = True,
    local_offset_hours: int | None = None,
    **_legacy,
) -> str:
    """Render a trade_ens-only alert body (no regime labels)."""
    if signal not in TRADE_SIGNALS:
        signal = "NO_TRADE"
    lines = ["<b>GMRAI · XAUUSD M15 · TRADE_ENS</b>", f"Tín hiệu: <b>{signal}</b>"]
    if changed and previous_signal in TRADE_SIGNALS:
        lines.append(f"Trước đó: {previous_signal}")
    local = _fmt_ts_local(bar_ts, local_offset_hours) if local_offset_hours is not None else ""
    lines.append(f"Nến M15: {_fmt_ts(bar_ts)}" + (f" · {local} giờ máy" if local else ""))
    lines.append(f"Giá đóng: {_fmt_price(price)}")
    if p_long is not None and p_short is not None:
        lines.append(f"p(LONG)={p_long * 100:.1f}% · p(SHORT)={p_short * 100:.1f}%")
    if threshold is not None:
        lines.append(f"Threshold SHORT: {threshold * 100:.1f}%")
    if stale:
        lines.append("<b>CẢNH BÁO: dữ liệu M15 đã cũ</b>")
    lines.extend(
        [
            "",
            "<i>Nghiên cứu — không phải lời khuyên đầu tư, không gửi lệnh. "
            "Risk/lệnh và max daily loss do EA xử lý.</i>",
        ]
    )
    return "\n".join(lines)


def _existing(db: Session, dedupe_key: str) -> TelegramMessage | None:
    return db.query(TelegramMessage).filter(TelegramMessage.dedupe_key == dedupe_key).first()


def _last_sent(db: Session, symbol: str) -> TelegramMessage | None:
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
        signal=signal if signal in TRADE_SIGNALS else "NO_TRADE",
        previous_signal=previous_signal if previous_signal in TRADE_SIGNALS else None,
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
        db.rollback()
        found = _existing(db, dedupe_key)
        if found is not None:
            return found
        raise
    return msg


def notify_signal(
    db: Session,
    symbol: str = "XAUUSD",
    include_forecast: bool = True,  # kept for API compatibility; never used
    alert_max_age_seconds: int | None = None,
) -> dict:
    """Send the latest trade_ens signal if it is new for this bar."""
    try:
        sig = compute_latest_signal(db)
    except TradeSignalError as e:
        return {"status": "skipped", "reason": e.code}

    signal = sig.get("signal", "NO_TRADE")
    if signal not in TRADE_SIGNALS:
        signal = "NO_TRADE"
    bar_raw = sig.get("bar_ts")
    if isinstance(bar_raw, str):
        try:
            bar_ts = datetime.fromisoformat(bar_raw.replace("Z", "+00:00"))
        except ValueError:
            bar_ts = None
    else:
        bar_ts = ensure_utc(bar_raw) if bar_raw else None
    dedupe_key = f"trade_ens:{symbol}:{bar_ts.isoformat() if bar_ts else 'none'}:{signal}"
    existing = _existing(db, dedupe_key)
    if existing is not None:
        return {"status": "skipped", "reason": "already_logged_for_bar", "id": existing.id}

    last = _last_sent(db, symbol)
    previous_signal = last.signal if last and last.signal in TRADE_SIGNALS else None
    price = float(sig.get("price")) if sig.get("price") is not None else None
    confidence = max(float(sig.get("p_long", 0)), float(sig.get("p_short", 0)))
    stale = bool(sig.get("stale"))
    threshold = float(sig.get("threshold")) if sig.get("threshold") is not None else None
    text = render_signal_message(
        signal=signal,
        previous_signal=previous_signal,
        bar_ts=bar_ts,
        price=price,
        confidence=confidence,
        p_long=float(sig.get("p_long", 0)),
        p_short=float(sig.get("p_short", 0)),
        threshold=threshold,
        stale=stale,
        changed=previous_signal != signal,
        local_offset_hours=settings.telegram_local_offset_hours,
    )

    if stale:
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
            confidence=confidence,
            reason="stale_data",
        )
        return {"status": "skipped", "reason": "stale_data", "id": msg.id}

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
            confidence=confidence,
            reason="telegram_disabled" if not settings.telegram_enabled else "not_configured",
        )
        return {"status": "skipped", "reason": msg.reason, "id": msg.id}

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
        confidence=confidence,
        message_id=message_id,
        error=error,
    )
    return {
        "status": "sent" if ok else "failed",
        "reason": None if ok else error,
        "id": msg.id,
        "signal": signal,
    }


def send_test_message(db: Session) -> dict:
    text = (
        "<b>GMRAI · TRADE_ENS test</b>\n"
        "Kênh Telegram đã kết nối.\n"
        "<i>Chỉ gửi LONG / SHORT / NO_TRADE.</i>"
    )
    if not settings.telegram_enabled or not is_configured():
        return {
            "status": "skipped",
            "reason": "telegram_disabled" if not settings.telegram_enabled else "not_configured",
        }
    ok, message_id, error = _post(text)
    msg = _record(
        db,
        dedupe_key=f"test:{utcnow().isoformat()}",
        kind="test",
        status="sent" if ok else "failed",
        text=text,
        message_id=message_id,
        error=error,
    )
    return {
        "status": "sent" if ok else "failed",
        "id": msg.id,
        "message_id": message_id,
        "error": error,
    }


def telegram_status(db: Session) -> dict:
    rows = db.query(TelegramMessage).order_by(TelegramMessage.id.desc()).limit(500).all()
    counts = {
        "total": len(rows),
        "sent": sum(1 for r in rows if r.status == "sent"),
        "skipped": sum(1 for r in rows if r.status == "skipped"),
        "failed": sum(1 for r in rows if r.status == "failed"),
    }
    last = rows[0] if rows else None
    try:
        sig = compute_latest_signal(db)
        latest = {
            "signal": sig.get("signal", "NO_TRADE"),
            "bar_ts": sig.get("bar_ts"),
            "p_long": sig.get("p_long"),
            "p_short": sig.get("p_short"),
            "threshold": sig.get("threshold"),
            "stale": sig.get("stale"),
        }
    except TradeSignalError:
        latest = None
    return {
        "enabled": bool(settings.telegram_enabled),
        "configured": is_configured(),
        "chat_id": settings.telegram_chat_id or None,
        "counts": counts,
        "last": None
        if last is None
        else {
            "id": last.id,
            "status": last.status,
            "signal": last.signal if last.signal in TRADE_SIGNALS else "NO_TRADE",
            "reason": last.reason,
            "created_at": ensure_utc(last.created_at).isoformat(),
            "error": last.error,
        },
        "latest_signal": latest,
        "note": "Telegram only receives LONG / SHORT / NO_TRADE from trade_ens.",
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
                "signal": r.signal if r.signal in TRADE_SIGNALS else "NO_TRADE",
                "previous_signal": r.previous_signal if r.previous_signal in TRADE_SIGNALS else None,
                "bar_ts": ensure_utc(r.bar_ts).isoformat() if r.bar_ts else None,
                "price": r.price,
                "confidence": r.confidence,
                "text": r.text,
                "reason": r.reason,
                "message_id": r.message_id,
                "error": r.error,
                "created_at": ensure_utc(r.created_at).isoformat() if r.created_at else None,
                "sent_at": ensure_utc(r.sent_at).isoformat() if r.sent_at else None,
            }
            for r in rows
        ],
    }
