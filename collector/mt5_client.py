"""MT5 terminal client — wraps the MetaTrader5 package (Windows only).

The collector ATTACHES to an already-running MT5 Terminal where the user
has logged into FTMO manually. Credentials are NEVER required in chat;
if MT5_LOGIN/MT5_PASSWORD/MT5_SERVER are set locally in .env, an automatic
login is attempted, otherwise the user must log in via the terminal UI.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import MetaTrader5 as mt5  # type: ignore  # Windows-only package

logger = logging.getLogger("gmrai.collector.mt5")

TIMEFRAMES = {
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "H1": mt5.TIMEFRAME_H1,
}


class Mt5Unavailable(RuntimeError):
    pass


class Mt5FetchError(RuntimeError):
    """copy_rates_* rejected the request (params/history issue) — connection is fine."""


class Mt5Client:
    def __init__(self, symbol: str, mt5_path: str = "", login: int | None = None,
                 password: str = "", server: str = ""):
        self.symbol = symbol
        self.mt5_path = mt5_path
        self.login = login
        self.password = password
        self.server = server

    # ---- lifecycle ----

    def initialize(self) -> bool:
        """Attach to the running MT5 terminal (or start it via mt5_path)."""
        kwargs: dict[str, Any] = {}
        if self.mt5_path:
            kwargs["path"] = self.mt5_path
        if not mt5.initialize(**kwargs):
            raise Mt5Unavailable(f"MT5 initialize failed: {mt5.last_error()}")

        info = mt5.terminal_info()
        if info is None or not getattr(info, "connected", False):
            raise Mt5Unavailable("MT5 terminal is not connected to a trade server")

        account = mt5.account_info()
        if account is None:
            # try automatic login only when credentials are configured locally
            if self.login and self.password and self.server:
                if not mt5.login(self.login, password=self.password, server=self.server):
                    raise Mt5Unavailable(
                        "MT5 auto-login failed — log in manually in the MT5 Terminal"
                        " (FTMO credentials are never required in chat; configure"
                        " them locally in collector/.env)"
                    )
            else:
                raise Mt5Unavailable(
                    "MT5 not logged in — log in manually in the MT5 Terminal, or set"
                    " MT5_LOGIN/MT5_PASSWORD/MT5_SERVER in collector/.env"
                )
        logger.info("MT5 connected: account=%s server=%s", account.login, account.server)
        return True

    def ensure_symbol(self) -> None:
        info = mt5.symbol_info(self.symbol)
        if info is None:
            raise Mt5Unavailable(
                f"Symbol {self.symbol} not visible — add it to Market Watch in MT5"
            )
        # Subscribe in Market Watch so history requests work reliably.
        if not mt5.symbol_select(self.symbol, True):
            logger.warning("symbol_select(%s) failed: %s", self.symbol, mt5.last_error())

    def shutdown(self) -> None:
        mt5.shutdown()

    # ---- data ----

    def fetch_range(self, timeframe: str, start: datetime, end: datetime) -> list[dict]:
        """Raw bars in [start, end]; converts MT5 numpy rows to dicts (UTC)."""
        if timeframe not in TIMEFRAMES:
            raise ValueError(f"Unsupported timeframe {timeframe}")
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("start/end must be timezone-aware (UTC)")
        start = start.replace(microsecond=0)
        end = end.replace(microsecond=0)
        rates = mt5.copy_rates_range(self.symbol, TIMEFRAMES[timeframe], start, end)
        if rates is None:
            err = mt5.last_error()
            if err and err[0] != 0:
                raise Mt5FetchError(
                    f"copy_rates_range({timeframe}, {start.isoformat()}, {end.isoformat()})"
                    f" failed: {err}"
                )
            return []
        bars = []
        for row in rates:
            bars.append(
                {
                    "ts": datetime.fromtimestamp(int(row["time"]), tz=timezone.utc),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "tick_volume": int(row["tick_volume"]),
                    "spread": int(row["spread"]),
                    "real_volume": int(row["real_volume"]) if "real_volume" in row.dtype.names else None,
                }
            )
        return bars

    def reconnect(self) -> bool:
        """Recover after a dropped connection: re-initialize."""
        try:
            self.shutdown()
        except Exception:
            pass
        try:
            return self.initialize()
        except Mt5Unavailable:
            return False

    def get_tick(self) -> dict | None:
        """Latest Bid/Ask tick (display-only, not used for analysis)."""
        info = mt5.symbol_info_tick(self.symbol)
        if info is None:
            return None
        return {
            "symbol": self.symbol,
            "bid": float(info.bid),
            "ask": float(info.ask),
            "last": float(info.last) if info.last else float(info.bid),
            "spread": int(getattr(info, "spread", 0) or 0),
        }
