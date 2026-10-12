"""Central logging configuration - structured, consistent, and quiet in the right places."""
import logging
import sys

from .config import settings

FMT = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"


def setup_logging() -> None:
    root = logging.getLogger()
    if root.handlers:  # already configured (e.g. reload)
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(FMT, datefmt="%Y-%m-%d %H:%M:%S"))
    root.addHandler(handler)
    root.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
    # tone down noisy libraries
    for noisy in ("uvicorn.access", "httpx", "pymongo"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
