"""Standalone worker process entry point (docker-compose `worker` service).

Production can swap the in-process scheduler for Celery later without
changing job functions (see docs/ARCHITECTURE.md, decision A6).
"""
from __future__ import annotations

import logging
import signal
import threading
import time

from app.config import settings
from app.db import Base, get_engine
from app.services.worker import worker

logger = logging.getLogger("gmrai.worker_main")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    get_engine()
    Base.metadata.create_all(get_engine())
    worker.start_scheduler()

    stop = threading.Event()

    def _sig(signum, frame):
        logger.info("Signal %s — stopping worker", signum)
        stop.set()

    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)

    logger.info("GMRAI worker running (automation=%s)", settings.automation_enabled)
    while not stop.wait(1):
        pass
    worker.stop()


if __name__ == "__main__":
    main()
