"""Unit tests for slash command registration."""

from __future__ import annotations

import discord
from discord import app_commands

from cadence.commands import COMMAND_NAMES, register
from cadence.commands.deps import CommandDeps
from cadence.state import StateStore
from tests.fakes import FakeAudioSource, FakePlayer


def test_register_attaches_exactly_nine_commands() -> None:
    client = discord.Client(intents=discord.Intents.default())
    tree = app_commands.CommandTree(client)
    deps = CommandDeps(
        player=FakePlayer(),
        source=FakeAudioSource(),
        store=StateStore(),
    )

    register(tree, deps)

    names = {command.name for command in tree.get_commands()}
    assert names == set(COMMAND_NAMES)
    assert len(tree.get_commands()) == 9
