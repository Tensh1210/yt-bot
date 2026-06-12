"""Central configuration loaded once at startup.

All environment variables are parsed here so invalid values fail fast when the
bot starts instead of silently falling back to defaults somewhere mid-runtime.
Call init_config() right after load_dotenv(); consumers use get_config().
"""

from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_COMMAND_PREFIX = "!"
DEFAULT_SEARCH_PROVIDER = "ytdlp"
DEFAULT_MAX_QUEUE_SIZE = 200
DEFAULT_MAX_PLAYLIST_ITEMS = 200
DEFAULT_PLAYLIST_LOOKUP_TIMEOUT_SECONDS = 30
DEFAULT_IDLE_DISCONNECT_SECONDS = 300

VALID_SEARCH_PROVIDERS = {"ytdlp", "ytmusic"}


class ConfigError(Exception):
    """Raised at startup when an environment variable holds an invalid value."""


@dataclass(frozen=True)
class Config:
    discord_token: str
    command_prefix: str
    sync_slash_commands: bool
    discord_guild_id: int | None
    search_provider: str
    max_queue_size: int
    max_playlist_items: int
    playlist_lookup_timeout_seconds: int
    playlist_shuffle: bool
    idle_disconnect_seconds: int


def _parse_int(name: str, default: int, minimum: int) -> int:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw_value!r}.") from exc
    if value < minimum:
        raise ConfigError(f"{name} must be >= {minimum}, got {value}.")
    return value


def _parse_flag(name: str, default: bool) -> bool:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    if raw_value not in {"0", "1"}:
        raise ConfigError(f"{name} must be 0 or 1, got {raw_value!r}.")
    return raw_value == "1"


def load_config() -> Config:
    """Parse all environment variables, raising ConfigError on any invalid value."""
    discord_token = os.getenv("DISCORD_TOKEN", "").strip()
    if not discord_token:
        raise ConfigError("DISCORD_TOKEN is required.")

    discord_guild_id: int | None = None
    guild_id_raw = os.getenv("DISCORD_GUILD_ID", "").strip()
    if guild_id_raw:
        try:
            discord_guild_id = int(guild_id_raw)
        except ValueError as exc:
            raise ConfigError("DISCORD_GUILD_ID must be a numeric Discord server ID.") from exc

    search_provider = os.getenv("SEARCH_PROVIDER", "").strip().lower() or DEFAULT_SEARCH_PROVIDER
    if search_provider not in VALID_SEARCH_PROVIDERS:
        raise ConfigError(
            f"SEARCH_PROVIDER must be one of {sorted(VALID_SEARCH_PROVIDERS)}, got {search_provider!r}."
        )

    return Config(
        discord_token=discord_token,
        command_prefix=os.getenv("COMMAND_PREFIX", "").strip() or DEFAULT_COMMAND_PREFIX,
        sync_slash_commands=_parse_flag("SYNC_SLASH_COMMANDS", default=True),
        discord_guild_id=discord_guild_id,
        search_provider=search_provider,
        max_queue_size=_parse_int("MAX_QUEUE_SIZE", DEFAULT_MAX_QUEUE_SIZE, minimum=1),
        max_playlist_items=_parse_int("MAX_PLAYLIST_ITEMS", DEFAULT_MAX_PLAYLIST_ITEMS, minimum=1),
        playlist_lookup_timeout_seconds=_parse_int(
            "PLAYLIST_LOOKUP_TIMEOUT_SECONDS", DEFAULT_PLAYLIST_LOOKUP_TIMEOUT_SECONDS, minimum=1
        ),
        playlist_shuffle=_parse_flag("PLAYLIST_SHUFFLE", default=True),
        # 0 disables the idle auto-leave entirely.
        idle_disconnect_seconds=_parse_int(
            "IDLE_DISCONNECT_SECONDS", DEFAULT_IDLE_DISCONNECT_SECONDS, minimum=0
        ),
    )


_config: Config | None = None


def init_config() -> Config:
    """Load and cache the config. Must run after load_dotenv() at startup."""
    global _config
    _config = load_config()
    return _config


def get_config() -> Config:
    if _config is None:
        raise RuntimeError("Config is not initialized; call init_config() at startup first.")
    return _config
