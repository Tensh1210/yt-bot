from __future__ import annotations

import asyncio

import pytest

import core.ytdlp_source as source
from core.ytdlp_source import Track, TrackLookupError, resolve_track


@pytest.fixture(autouse=True)
def clear_cache():
    source._resolve_cache.clear()
    yield
    source._resolve_cache.clear()


@pytest.fixture
def extract_calls(monkeypatch):
    """Replace the yt-dlp extraction with a recorder returning a fixed Track."""
    calls: list[str] = []

    def fake_extract(query: str) -> Track:
        calls.append(query)
        return Track(title="T", webpage_url="https://www.youtube.com/watch?v=abc", stream_url="https://stream")

    monkeypatch.setattr(source, "_extract", fake_extract)
    return calls


def test_second_resolve_hits_cache(extract_calls):
    first = asyncio.run(resolve_track("some song"))
    second = asyncio.run(resolve_track("some song"))
    assert first == second
    assert extract_calls == ["some song"]


def test_cache_also_keyed_by_webpage_url(extract_calls):
    resolved = asyncio.run(resolve_track("some song"))
    again = asyncio.run(resolve_track(resolved.webpage_url))
    assert again == resolved
    assert extract_calls == ["some song"]


def test_expired_entry_re_resolves(extract_calls):
    asyncio.run(resolve_track("some song"))
    # Rewind every entry's expiry into the past.
    for key, (track, _) in list(source._resolve_cache.items()):
        source._resolve_cache[key] = (track, 0.0)
    asyncio.run(resolve_track("some song"))
    assert extract_calls == ["some song", "some song"]


def test_cache_evicts_oldest_beyond_cap(monkeypatch, extract_calls):
    monkeypatch.setattr(source, "RESOLVE_CACHE_MAX_ENTRIES", 3)
    for index in range(4):
        asyncio.run(resolve_track(f"song {index}"))
    assert len(source._resolve_cache) <= 3
    # The oldest query was evicted and resolves again.
    asyncio.run(resolve_track("song 0"))
    assert extract_calls.count("song 0") == 2


def test_failed_resolve_is_not_cached(monkeypatch):
    calls: list[str] = []

    def failing_extract(query: str) -> Track:
        calls.append(query)
        raise TrackLookupError("nope")

    monkeypatch.setattr(source, "_extract", failing_extract)
    for _ in range(2):
        with pytest.raises(TrackLookupError):
            asyncio.run(resolve_track("bad song"))
    assert len(calls) == 2
