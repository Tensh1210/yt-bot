from __future__ import annotations

import pytest

import core.config
from core.config import ConfigError, get_config, init_config, load_config


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Strip every bot variable so each test controls its own environment."""
    for name in (
        "DISCORD_TOKEN",
        "COMMAND_PREFIX",
        "SYNC_SLASH_COMMANDS",
        "DISCORD_GUILD_ID",
        "SEARCH_PROVIDER",
        "MAX_QUEUE_SIZE",
        "MAX_PLAYLIST_ITEMS",
        "PLAYLIST_LOOKUP_TIMEOUT_SECONDS",
        "PLAYLIST_SHUFFLE",
        "IDLE_DISCONNECT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(core.config, "_config", None)


def test_defaults_with_only_token(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "x")
    config = load_config()
    assert config.command_prefix == "!"
    assert config.sync_slash_commands is True
    assert config.discord_guild_id is None
    assert config.search_provider == "ytdlp"
    assert config.max_queue_size == 200
    assert config.max_playlist_items == 200
    assert config.playlist_lookup_timeout_seconds == 30
    assert config.playlist_shuffle is True
    assert config.idle_disconnect_seconds == 300


def test_missing_token_fails():
    with pytest.raises(ConfigError, match="DISCORD_TOKEN"):
        load_config()


def test_explicit_values_parsed(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "x")
    monkeypatch.setenv("COMMAND_PREFIX", "?")
    monkeypatch.setenv("SYNC_SLASH_COMMANDS", "0")
    monkeypatch.setenv("DISCORD_GUILD_ID", "123456")
    monkeypatch.setenv("SEARCH_PROVIDER", "YTMusic")
    monkeypatch.setenv("MAX_QUEUE_SIZE", "5")
    monkeypatch.setenv("PLAYLIST_SHUFFLE", "0")
    monkeypatch.setenv("IDLE_DISCONNECT_SECONDS", "0")
    config = load_config()
    assert config.command_prefix == "?"
    assert config.sync_slash_commands is False
    assert config.discord_guild_id == 123456
    assert config.search_provider == "ytmusic"
    assert config.max_queue_size == 5
    assert config.playlist_shuffle is False
    assert config.idle_disconnect_seconds == 0


@pytest.mark.parametrize(
    ("name", "value", "match"),
    [
        ("MAX_QUEUE_SIZE", "abc", "must be an integer"),
        ("MAX_QUEUE_SIZE", "0", ">= 1"),
        ("MAX_PLAYLIST_ITEMS", "-5", ">= 1"),
        ("PLAYLIST_LOOKUP_TIMEOUT_SECONDS", "0", ">= 1"),
        ("IDLE_DISCONNECT_SECONDS", "-1", ">= 0"),
        ("PLAYLIST_SHUFFLE", "yes", "must be 0 or 1"),
        ("SYNC_SLASH_COMMANDS", "true", "must be 0 or 1"),
        ("SEARCH_PROVIDER", "spotify", "SEARCH_PROVIDER"),
        ("DISCORD_GUILD_ID", "not-a-number", "numeric"),
    ],
)
def test_invalid_values_fail_fast(monkeypatch, name, value, match):
    monkeypatch.setenv("DISCORD_TOKEN", "x")
    monkeypatch.setenv(name, value)
    with pytest.raises(ConfigError, match=match):
        load_config()


def test_get_config_requires_init():
    with pytest.raises(RuntimeError, match="init_config"):
        get_config()


def test_init_config_caches(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "x")
    initialized = init_config()
    assert get_config() is initialized
