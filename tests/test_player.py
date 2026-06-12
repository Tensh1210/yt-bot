from __future__ import annotations

import asyncio

import pytest

import core.player
from core.player import GuildPlayer, QueuedTrack, QueueFullError, _to_track_request
from core.ytdlp_source import Track, TrackRequest


def run(coro):
    return asyncio.run(coro)


async def make_busy_player() -> GuildPlayer:
    """Player that behaves as if a track is mid-start, so enqueue only queues
    and never reaches the network/voice playback path."""
    player = GuildPlayer(guild_id=1, loop=asyncio.get_running_loop())
    player._starting = True
    return player


def make_track(index: int, stream_url: str | None = None) -> TrackRequest:
    return TrackRequest(
        title=f"Track {index}",
        webpage_url=f"https://www.youtube.com/watch?v=video{index}",
        stream_url=stream_url,
    )


VOICE_CHANNEL = object()  # enqueue only stores it; no voice methods are called


def test_to_track_request_keeps_resolved_stream_url():
    track = Track(title="T", webpage_url="https://w", stream_url="https://s")
    request = _to_track_request(track)
    assert request == TrackRequest(title="T", webpage_url="https://w", stream_url="https://s")


def test_to_track_request_passes_request_through():
    request = make_track(1)
    assert _to_track_request(request) is request


def test_enqueue_returns_queue_positions(app_config):
    async def scenario():
        player = await make_busy_player()
        first = await player.enqueue(make_track(1), VOICE_CHANNEL)
        second = await player.enqueue(make_track(2), VOICE_CHANNEL)
        return first, second

    assert run(scenario()) == (1, 2)


def test_enqueue_strips_stream_url_for_waiting_tracks(app_config):
    async def scenario():
        player = await make_busy_player()
        await player.enqueue(make_track(1, stream_url="https://expires-soon"), VOICE_CHANNEL)
        return player.queue[0].track.stream_url

    assert run(scenario()) is None


def test_enqueue_rejects_when_queue_full(app_config):
    app_config(max_queue_size=2)

    async def scenario():
        player = await make_busy_player()
        await player.enqueue(make_track(1), VOICE_CHANNEL)
        await player.enqueue(make_track(2), VOICE_CHANNEL)
        with pytest.raises(QueueFullError):
            await player.enqueue(make_track(3), VOICE_CHANNEL)

    run(scenario())


def test_enqueue_many_truncates_to_available_slots(app_config):
    app_config(max_queue_size=3)

    async def scenario():
        player = await make_busy_player()
        await player.enqueue(make_track(0), VOICE_CHANNEL)
        accepted = await player.enqueue_many([make_track(i) for i in range(1, 6)], VOICE_CHANNEL)
        return accepted, len(player.queue)

    accepted, queued = run(scenario())
    assert accepted == 2
    assert queued == 3


def test_enqueue_many_rejects_when_queue_full(app_config):
    app_config(max_queue_size=1)

    async def scenario():
        player = await make_busy_player()
        await player.enqueue(make_track(0), VOICE_CHANNEL)
        with pytest.raises(QueueFullError):
            await player.enqueue_many([make_track(1)], VOICE_CHANNEL)

    run(scenario())


def test_enqueue_many_tags_tracks_with_one_playlist_id(app_config):
    async def scenario():
        player = await make_busy_player()
        await player.enqueue_many([make_track(1), make_track(2)], VOICE_CHANNEL)
        return {queued.playlist_id for queued in player.queue}

    playlist_ids = run(scenario())
    assert len(playlist_ids) == 1
    assert None not in playlist_ids


def test_queue_summary_lists_current_and_upcoming(app_config):
    async def scenario():
        player = await make_busy_player()
        player.current = Track(title="Current Song", webpage_url="https://w", stream_url="https://s")
        for index in range(1, 13):
            player.queue.append(QueuedTrack(track=make_track(index), voice_channel=VOICE_CHANNEL))
        return await player.queue_summary(limit=10)

    summary = run(scenario())
    assert "Now playing: Current Song" in summary
    assert "Up next (12 queued):" in summary
    assert "1. Track 1" in summary
    assert "10. Track 10" in summary
    assert "Track 11" not in summary
    assert "...and 2 more." in summary


def test_queue_summary_when_idle(app_config):
    async def scenario():
        player = await make_busy_player()
        return await player.queue_summary()

    summary = run(scenario())
    assert "Nothing is playing." in summary
    assert "Queue is empty." in summary


@pytest.fixture
def resolved_urls(monkeypatch):
    """Record URLs the player resolves during prefetch instead of hitting yt-dlp."""
    urls: list[str] = []

    async def fake_resolve(url: str) -> Track:
        urls.append(url)
        return Track(title="T", webpage_url=url, stream_url="https://stream")

    monkeypatch.setattr(core.player, "resolve_track", fake_resolve)
    return urls


def test_enqueue_while_busy_prefetches_queue_head(app_config, resolved_urls):
    async def scenario():
        player = await make_busy_player()
        await player.enqueue(make_track(1), VOICE_CHANNEL)
        assert player._prefetch_task is not None
        await player._prefetch_task

    run(scenario())
    assert resolved_urls == ["https://www.youtube.com/watch?v=video1"]


def test_prefetch_not_rescheduled_while_head_unchanged(app_config, resolved_urls):
    async def scenario():
        player = await make_busy_player()
        await player.enqueue(make_track(1), VOICE_CHANNEL)
        first_task = player._prefetch_task
        # A second enqueue keeps the same head, so the running prefetch stays.
        await player.enqueue(make_track(2), VOICE_CHANNEL)
        assert player._prefetch_task is first_task
        await first_task

    run(scenario())
    assert resolved_urls == ["https://www.youtube.com/watch?v=video1"]


def test_stop_cancels_pending_prefetch(app_config, monkeypatch):
    async def never_resolve(url: str) -> Track:
        await asyncio.sleep(3600)
        raise AssertionError("unreachable")

    monkeypatch.setattr(core.player, "resolve_track", never_resolve)

    async def scenario():
        player = await make_busy_player()
        await player.enqueue(make_track(1), VOICE_CHANNEL)
        task = player._prefetch_task
        await player.stop()
        assert player._prefetch_task is None
        with pytest.raises(asyncio.CancelledError):
            await task

    run(scenario())


def test_controls_without_voice_client_report_nothing_playing(app_config):
    async def scenario():
        player = await make_busy_player()
        return await player.pause(), await player.resume(), await player.skip(), await player.skip_playlist()

    pause, resume, skip, skip_playlist = run(scenario())
    assert pause == "Nothing is playing."
    assert resume == "Nothing is paused."
    assert skip == "Nothing is playing."
    assert skip_playlist == "No playlist is currently playing."
