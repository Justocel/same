import logging
import os


def setup_logging(level: str | None = None) -> logging.Logger:
    """Call once at program start. Reads LOG_LEVEL from env (default INFO)."""
    logging.basicConfig(
        level=level or os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    )
    return logging.getLogger("same")
