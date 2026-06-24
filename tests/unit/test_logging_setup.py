"""Tests for cadence.logging_setup."""

from __future__ import annotations

import logging

from cadence.logging_setup import configure_logging


def test_configure_logging_sets_cadence_and_discord_levels() -> None:
    configure_logging(logging.DEBUG)
    assert logging.getLogger("cadence").level == logging.DEBUG
    assert logging.getLogger("discord").level == logging.WARNING
