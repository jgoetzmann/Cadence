"""Tests for cadence.client."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import discord
import pytest
from discord import app_commands

from cadence.client import build_client, sync_commands
from cadence.config import Settings


@dataclass
class FakeCommandTree:
    """Records sync calls without contacting Discord."""

    sync_calls: list[dict[str, Any]] = field(default_factory=list)
    copy_global_calls: list[discord.Object] = field(default_factory=list)

    def copy_global_to(self, *, guild: discord.Object) -> None:
        self.copy_global_calls.append(guild)

    async def sync(self, *, guild: discord.Object | None = None) -> list[app_commands.AppCommand]:
        self.sync_calls.append({"guild": guild})
        return []


@pytest.mark.asyncio
async def test_sync_commands_uses_guild_path_when_guild_id_set() -> None:
    tree = FakeCommandTree()
    settings = Settings(
        token="test-token",
        guild_id=123,
        log_level=20,
        default_volume=50,
    )
    await sync_commands(tree, settings)  # type: ignore[arg-type]
    assert len(tree.copy_global_calls) == 1
    assert tree.copy_global_calls[0].id == 123
    assert len(tree.sync_calls) == 1
    assert tree.sync_calls[0]["guild"] is not None
    assert tree.sync_calls[0]["guild"].id == 123


@pytest.mark.asyncio
async def test_sync_commands_uses_global_path_when_no_guild_id() -> None:
    tree = FakeCommandTree()
    settings = Settings(
        token="test-token",
        guild_id=None,
        log_level=20,
        default_volume=50,
    )
    await sync_commands(tree, settings)  # type: ignore[arg-type]
    assert tree.copy_global_calls == []
    assert len(tree.sync_calls) == 1
    assert tree.sync_calls[0]["guild"] is None


def test_build_client_returns_client_and_tree() -> None:
    settings = Settings(
        token="test-token",
        guild_id=None,
        log_level=20,
        default_volume=50,
    )
    client, tree = build_client(settings)
    assert isinstance(client, discord.Client)
    assert isinstance(tree, app_commands.CommandTree)
    assert tree.client is client
