"""Collector main loop: init MT5 -> sync all timeframes -> sleep -> repeat.

Recovers from MT5 disconnects (re-init + retry with backoff). Graceful stop
on SIGINT/SIGTERM. Checkpoints guarantee progress after restart.
"""
from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from datetime import timedelta, timezone

from api_client import ApiClient, ApiClientError
from config import load_config
from data_sync import CheckpointStore, run_sync
from logger import setup_logging
from mt5_client import Mt5Client, Mt5Unavailable

logger = logging.getLogger("gmrai.collector")

_stop = False


def _handle_signal(signum, frame):
    global _stop
    logger.info("Signal %s received — stopping after current cycle", signum)
    _stop = True


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="GMRAI FTMO MT5 data collector")
    ap.add_argument("--backfill", type=int, metavar="DAYS",
                    help="reset checkpoints and backfill N days of history")
    ap.add_argument("--once", action="store_true", help="run one sync cycle and exit")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    cfg = load_config()
    logger = setup_logging(cfg.log_dir, cfg.log_level)
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    logger.info("GMRAI collector starting: symbol=%s tfs=%s url=%s",
                cfg.symbol, cfg.timeframes, cfg.api_url)

    if cfg.backfill_days or args.backfill:
        days = args.backfill or cfg.backfill_days or cfg.history_days
        checkpoint = CheckpointStore(cfg.checkpoint_dir)
        for tf in cfg.timeframes:
            checkpoint.reset(cfg.symbol, tf)
        logger.info("Backfill mode: checkpoints reset, %d days requested", days)
        cfg.backfill_days = days

    mt5_client = Mt5Client(
        cfg.symbol, cfg.mt5_path, cfg.mt5_login, cfg.mt5_password, cfg.mt5_server
    )
    api = ApiClient(cfg.api_url, cfg.api_key, cfg.collector_id)
    checkpoint = CheckpointStore(cfg.checkpoint_dir)

    connected = False
    retry_delay = 10
    while not _stop:
        try:
            if not connected:
                mt5_client.initialize()
                mt5_client.ensure_symbol()
                connected = True
                retry_delay = 10
                logger.info("MT5 connection established for %s", cfg.symbol)

            for tf in cfg.timeframes:
                result = run_sync(
                    lambda sym, tf, s, e: mt5_client.fetch_range(tf, s, e),
                    api.send_candles,
                    checkpoint,
                    cfg.symbol,
                    tf,
                    now=__import__("datetime").datetime.now(timezone.utc),
                    resync_bars=cfg.resync_bars,
                    history_days=cfg.backfill_days,
                )
                logger.info(
                    "sync %s: fetched=%d closed=%d sent=%d inserted=%d updated=%d gaps=%d",
                    tf, result["fetched"], result["closed"], result["sent"],
                    result["inserted"], result["updated"], result["gap_count"],
                )

            if args.once:
                break
            time.sleep(cfg.sync_interval_seconds)

        except (Mt5Unavailable, ApiClientError) as e:
            logger.error("Sync error: %s — reconnecting in %ds", e, retry_delay)
            connected = False
            try:
                mt5_client.shutdown()
            except Exception:
                pass
            for _ in range(retry_delay):
                if _stop:
                    break
                time.sleep(1)
            retry_delay = min(retry_delay * 2, 300)
        except Exception as e:  # unexpected — log and keep going, never crash silently
            logger.exception("Unexpected error: %s", e)
            time.sleep(30)

    mt5_client.shutdown()
    logger.info("Collector stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
