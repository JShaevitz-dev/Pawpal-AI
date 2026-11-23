"""Send PawPal+ log records to logs/pawpal.log (and optionally the console)."""

from __future__ import annotations

import logging
from pathlib import Path

DEFAULT_LOG = Path(__file__).resolve().parent.parent / "logs" / "pawpal.log"


def setup_logging(path: str | Path = DEFAULT_LOG, level: int = logging.INFO, console: bool = False) -> Path:
    """Configure the 'pawpal' logger once. Safe to call more than once (e.g. on Streamlit reruns)."""
    logger = logging.getLogger("pawpal")
    logger.setLevel(level)
    path = Path(path)
    if not any(isinstance(h, logging.FileHandler) and Path(h.baseFilename) == path.resolve() for h in logger.handlers):
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
    if console and not any(type(h) is logging.StreamHandler for h in logger.handlers):
        stream = logging.StreamHandler()
        stream.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        logger.addHandler(stream)
    return path
