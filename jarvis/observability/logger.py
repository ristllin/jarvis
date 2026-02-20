import structlog
import logging
import sys
import os
import json
from datetime import datetime, timezone


def setup_logging():
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )


def get_logger(name: str = "jarvis"):
    return structlog.get_logger(name)


class FileLogger:
    """Append-only JSON-lines logger to /data/logs/"""

    def __init__(self, data_dir: str = "/data"):
        self.log_dir = os.path.join(data_dir, "logs")
        os.makedirs(self.log_dir, exist_ok=True)

    def log(self, event: str, **kwargs):
        now = datetime.now(timezone.utc)
        filename = now.strftime("%Y-%m-%d.jsonl")
        entry = {
            "timestamp": now.isoformat(),
            "event": event,
            **kwargs,
        }
        filepath = os.path.join(self.log_dir, filename)
        with open(filepath, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
