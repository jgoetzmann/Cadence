"""Tests for cadence.__main__."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cadence.__main__ import main
from cadence.config import ConfigError


def test_main_exits_when_settings_missing() -> None:
    with (
        patch(
            "cadence.__main__.Settings.load",
            side_effect=ConfigError("DISCORD_TOKEN is required"),
        ),
        pytest.raises(SystemExit, match="DISCORD_TOKEN is required"),
    ):
        main()


def test_main_runs_client_with_loaded_settings() -> None:
    settings = MagicMock()
    settings.token = "test-token"
    client = MagicMock()
    with (
        patch("cadence.__main__.Settings.load", return_value=settings),
        patch("cadence.__main__.build_app", return_value=client) as build_app,
    ):
        main()
    build_app.assert_called_once_with(settings)
    client.run.assert_called_once_with("test-token")
