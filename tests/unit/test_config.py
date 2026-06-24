"""Tests for cadence.config."""

from __future__ import annotations

import logging

import pytest

from cadence.config import ConfigError, Settings


def test_load_raises_when_discord_token_missing() -> None:
    with pytest.raises(ConfigError, match="DISCORD_TOKEN"):
        Settings.load()


def test_load_succeeds_with_token_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    settings = Settings.load()
    assert settings.token == "test-token"
    assert settings.guild_id is None
    assert settings.log_level == logging.INFO
    assert settings.default_volume == 50


def test_optional_vars_default_correctly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    settings = Settings.load()
    assert settings.guild_id is None
    assert settings.log_level == logging.INFO
    assert settings.default_volume == 50


def test_default_volume_clamped_to_100(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    monkeypatch.setenv("CADENCE_DEFAULT_VOLUME", "150")
    settings = Settings.load()
    assert settings.default_volume == 100


def test_default_volume_clamped_to_0(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    monkeypatch.setenv("CADENCE_DEFAULT_VOLUME", "-5")
    settings = Settings.load()
    assert settings.default_volume == 0


def test_guild_id_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    monkeypatch.setenv("DISCORD_GUILD_ID", "123456789012345678")
    settings = Settings.load()
    assert settings.guild_id == 123456789012345678


def test_invalid_guild_id_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    monkeypatch.setenv("DISCORD_GUILD_ID", "not-a-number")
    with pytest.raises(ConfigError, match="DISCORD_GUILD_ID"):
        Settings.load()


def test_log_level_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    settings = Settings.load()
    assert settings.log_level == logging.DEBUG


def test_invalid_log_level_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    monkeypatch.setenv("LOG_LEVEL", "NOT_A_LEVEL")
    with pytest.raises(ConfigError, match="LOG_LEVEL"):
        Settings.load()


def test_invalid_default_volume_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    monkeypatch.setenv("CADENCE_DEFAULT_VOLUME", "loud")
    with pytest.raises(ConfigError, match="CADENCE_DEFAULT_VOLUME"):
        Settings.load()


def test_settings_repr_never_includes_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", "super-secret-token")
    settings = Settings.load()
    text = repr(settings)
    assert "super-secret-token" not in text
    assert "token" not in text.lower()


def test_settings_str_matches_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    settings = Settings.load()
    assert str(settings) == repr(settings)
