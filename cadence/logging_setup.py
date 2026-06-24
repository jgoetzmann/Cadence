"""Logging configuration for Cadence."""

from __future__ import annotations

import logging

__all__ = ["configure_logging"]


def configure_logging(level: int) -> None:
    """Configure stdlib logging for the Cadence process."""
    logging.basicConfig(
        level=level,
        format="%(levelname)s %(name)s: %(message)s",
        force=True,
    )
    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("cadence").setLevel(level)
