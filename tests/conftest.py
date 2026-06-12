from __future__ import annotations

from dataclasses import replace

import pytest

import core.config
from core.config import Config


def _base_config() -> Config:
    return Config(
        discord_token="test-token",
        command_prefix="!",
        sync_slash_commands=True,
        discord_guild_id=None,
        search_provider="ytdlp",
        max_queue_size=200,
        max_playlist_items=200,
        playlist_lookup_timeout_seconds=30,
        playlist_shuffle=True,
        idle_disconnect_seconds=300,
    )


@pytest.fixture
def app_config(monkeypatch):
    """Install a test Config as the active singleton; override fields per test.

    Usage: app_config(max_queue_size=2) — returns the installed Config.
    """

    def install(**overrides) -> Config:
        config = replace(_base_config(), **overrides)
        monkeypatch.setattr(core.config, "_config", config)
        return config

    install()
    return install
