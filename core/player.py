from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import deque
from dataclasses import dataclass, replace

import discord

from core.ytdlp_source import Track, TrackLookupError, TrackRequest, resolve_track


DISCORD_MESSAGE_LIMIT = 2000
MAX_PLAYBACK_FAILURES = 2
DEFAULT_MAX_QUEUE_SIZE = 200
DEFAULT_IDLE_DISCONNECT_SECONDS = 300

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


@dataclass
class QueuedTrack:
    track: TrackRequest
    voice_channel: discord.VoiceChannel | discord.StageChannel
    notify_channel: discord.abc.Messageable | None = None
    playlist_id: int | None = None


class PlaybackStartError(Exception):
    pass


class QueueFullError(Exception):
    pass


def _max_queue_size() -> int:
    raw_value = os.getenv("MAX_QUEUE_SIZE", str(DEFAULT_MAX_QUEUE_SIZE))
    try:
        value = int(raw_value)
    except ValueError:
        return DEFAULT_MAX_QUEUE_SIZE
    return max(1, value)


def _idle_disconnect_seconds() -> int:
    """Seconds to stay in voice after the queue empties; 0 disables auto-leave."""
    raw_value = os.getenv("IDLE_DISCONNECT_SECONDS", str(DEFAULT_IDLE_DISCONNECT_SECONDS))
    try:
        value = int(raw_value)
    except ValueError:
        return DEFAULT_IDLE_DISCONNECT_SECONDS
    return max(0, value)


def _to_track_request(track: Track | TrackRequest) -> TrackRequest:
    if isinstance(track, TrackRequest):
        return track
    return TrackRequest(title=track.title, webpage_url=track.webpage_url, stream_url=track.stream_url)


class GuildPlayer:
    def __init__(self, guild_id: int, loop: asyncio.AbstractEventLoop) -> None:
        self.guild_id = guild_id
        self.loop = loop
        self.queue: deque[QueuedTrack] = deque()
        self.lock = asyncio.Lock()
        self.voice_client: discord.VoiceClient | None = None
        self.current: Track | None = None
        self._stop_requested = False
        self._playback_generation = 0
        self._playback_failures = 0
        self._playlist_counter = 0
        self._current_playlist_id: int | None = None
        # True while a popped track is being resolved/started outside the lock;
        # prevents a second concurrent playback start from racing it.
        self._starting = False
        # Disconnects from voice after the queue stays empty for a while.
        self._idle_timer: asyncio.Task | None = None

    async def enqueue(
        self,
        track: Track | TrackRequest,
        voice_channel: discord.VoiceChannel | discord.StageChannel,
        notify_channel: discord.abc.Messageable | None = None,
    ) -> int:
        async with self.lock:
            if len(self.queue) >= _max_queue_size():
                raise QueueFullError(f"Queue is full. Limit is {_max_queue_size()} tracks.")

            request = _to_track_request(track)
            start_now = self._idle_locked()
            if not start_now:
                # Stream URLs expire after a few hours. A track that has to wait
                # in the queue drops its pre-resolved URL and is re-resolved
                # right before playback instead.
                request = replace(request, stream_url=None)

            self.queue.append(
                QueuedTrack(track=request, voice_channel=voice_channel, notify_channel=notify_channel)
            )
            position = len(self.queue)
            next_item = self._take_next_locked() if start_now else None

        if next_item is None:
            return position

        queued, generation = next_item
        await self._drive_playback(queued, generation, raise_on_error=True)
        return 0

    async def enqueue_many(
        self,
        tracks: list[TrackRequest],
        voice_channel: discord.VoiceChannel | discord.StageChannel,
        notify_channel: discord.abc.Messageable | None = None,
    ) -> int:
        async with self.lock:
            if not tracks:
                return 0

            max_queue_size = _max_queue_size()
            available_slots = max_queue_size - len(self.queue)
            if available_slots <= 0:
                raise QueueFullError(f"Queue is full. Limit is {max_queue_size} tracks.")

            self._playlist_counter += 1
            pid = self._playlist_counter
            accepted_tracks = tracks[:available_slots]
            for track in accepted_tracks:
                self.queue.append(
                    QueuedTrack(
                        track=_to_track_request(track),
                        voice_channel=voice_channel,
                        notify_channel=notify_channel,
                        playlist_id=pid,
                    )
                )
            next_item = self._take_next_locked() if self._idle_locked() else None

        if next_item is not None:
            queued, generation = next_item
            await self._drive_playback(queued, generation, raise_on_error=True)

        return len(accepted_tracks)

    async def now_playing(self) -> str:
        async with self.lock:
            if self.current is None:
                return "Nothing is playing."
            return f"Now playing: {self.current.title}"

    async def pause(self) -> str:
        async with self.lock:
            if self.voice_client is None or not self.voice_client.is_playing():
                return "Nothing is playing."

            self.voice_client.pause()
            return "Paused."

    async def resume(self) -> str:
        async with self.lock:
            if self.voice_client is None or not self.voice_client.is_paused():
                return "Nothing is paused."

            self.voice_client.resume()
            return "Resumed."

    async def skip(self) -> str:
        async with self.lock:
            if self.voice_client is None or (not self.voice_client.is_playing() and not self.voice_client.is_paused()):
                return "Nothing is playing."

            skipped = self.current.title if self.current else "current track"
            self.voice_client.stop()
            return f"Skipped: {skipped}"

    async def skip_playlist(self) -> str:
        async with self.lock:
            if self._current_playlist_id is None:
                return "No playlist is currently playing."

            pid = self._current_playlist_id
            removed = sum(1 for q in self.queue if q.playlist_id == pid)
            self.queue = deque(q for q in self.queue if q.playlist_id != pid)
            self._current_playlist_id = None

            if self.voice_client and (self.voice_client.is_playing() or self.voice_client.is_paused()):
                self.voice_client.stop()

            return f"Skipped playlist. Removed {removed} tracks from queue."

    async def stop(self) -> str:
        async with self.lock:
            self.queue.clear()
            self.current = None
            self._stop_requested = True
            self._playback_generation += 1
            self._playback_failures = 0
            self._cancel_idle_timer_locked()

            if self.voice_client is not None:
                voice_client = self.voice_client
                self.voice_client = None

                if voice_client.is_playing() or voice_client.is_paused():
                    voice_client.stop()

                if voice_client.is_connected():
                    await voice_client.disconnect()

            return "Stopped playback and cleared the queue."

    async def queue_summary(self, limit: int = 10) -> str:
        async with self.lock:
            lines: list[str] = []

            if self.current:
                lines.append(f"Now playing: {self.current.title}")
            else:
                lines.append("Nothing is playing.")

            if self.queue:
                lines.append(f"Up next ({len(self.queue)} queued):")
                for index, queued in enumerate(list(self.queue)[:limit], start=1):
                    lines.append(f"{index}. {queued.track.title}")

                remaining = len(self.queue) - limit
                if remaining > 0:
                    lines.append(f"...and {remaining} more.")
            else:
                lines.append("Queue is empty.")

            summary = "\n".join(lines)
            if len(summary) > DISCORD_MESSAGE_LIMIT:
                return f"{summary[: DISCORD_MESSAGE_LIMIT - 3].rstrip()}..."
            return summary

    def _idle_locked(self) -> bool:
        """True when no track is playing, paused, or mid-start. Lock must be held."""
        if self._starting:
            return False
        return self.voice_client is None or (
            not self.voice_client.is_playing() and not self.voice_client.is_paused()
        )

    def _take_next_locked(self) -> tuple[QueuedTrack, int] | None:
        """Pop the next queued track and claim the start slot. Lock must be held.

        Returns the popped track with a generation snapshot used to detect a
        concurrent stop() while the track is resolved outside the lock.
        """
        if not self.queue:
            self.current = None
            self._playback_failures = 0
            self._current_playlist_id = None
            self._starting = False
            self._schedule_idle_disconnect_locked()
            return None

        queued = self.queue.popleft()
        self.current = None
        self._stop_requested = False
        self._current_playlist_id = queued.playlist_id
        self._starting = True
        self._cancel_idle_timer_locked()
        return queued, self._playback_generation

    def _cancel_idle_timer_locked(self) -> None:
        if self._idle_timer is not None:
            self._idle_timer.cancel()
            self._idle_timer = None

    def _schedule_idle_disconnect_locked(self) -> None:
        timeout = _idle_disconnect_seconds()
        if timeout <= 0 or self.voice_client is None:
            return
        self._cancel_idle_timer_locked()
        self._idle_timer = self.loop.create_task(self._idle_disconnect(timeout))

    async def _idle_disconnect(self, timeout: int) -> None:
        await asyncio.sleep(timeout)
        async with self.lock:
            self._idle_timer = None
            # Playback may have restarted while this timer waited for the lock.
            if not self._idle_locked() or self.queue:
                return

            voice_client = self.voice_client
            self.voice_client = None
            if voice_client is not None and voice_client.is_connected():
                await voice_client.disconnect()
                logging.info("Left voice in guild %s after %ss idle.", self.guild_id, timeout)

    async def _drive_playback(self, queued: QueuedTrack, generation: int, raise_on_error: bool) -> None:
        """Resolve popped tracks outside the lock, then start playback under it.

        The caller must have claimed the start slot via _take_next_locked().
        With raise_on_error the first failure raises PlaybackStartError;
        otherwise failed tracks are skipped with a notification until the queue
        empties or MAX_PLAYBACK_FAILURES consecutive failures occur.
        """
        while True:
            failure: str | None = None
            track: Track | None = None
            try:
                # Network lookup happens without the lock so pause/skip/queue
                # commands stay responsive during track transitions.
                track = await self._resolve_queued_track(queued)
            except TrackLookupError as exc:
                logging.warning("Could not resolve queued track in guild %s: %s", self.guild_id, exc)
                failure = f"Could not resolve queued track: {exc}"

            next_item: tuple[QueuedTrack, int] | None
            async with self.lock:
                if generation != self._playback_generation or self._stop_requested:
                    # stop() superseded this start while resolving; it already
                    # cleaned up, so just pick up anything enqueued afterwards.
                    next_item = self._take_next_locked()
                elif failure is None and self._current_playlist_id != queued.playlist_id:
                    # skipplaylist removed this playlist while the track was
                    # resolving; drop it silently and continue with the queue.
                    next_item = self._take_next_locked()
                else:
                    if failure is None and track is not None:
                        try:
                            await self._begin_playback_locked(queued.voice_channel, track)
                            self._starting = False
                            return
                        except PlaybackStartError as exc:
                            failure = str(exc)

                    if raise_on_error:
                        self._starting = False
                        raise PlaybackStartError(failure or "Could not start playback.")

                    self._playback_failures += 1
                    await self._notify(
                        queued.notify_channel,
                        f"Skipped unavailable track: {queued.track.title}. Trying next...",
                    )
                    if self._playback_failures >= MAX_PLAYBACK_FAILURES:
                        self.queue.clear()
                        self.current = None
                        self._starting = False
                        self._schedule_idle_disconnect_locked()
                        await self._notify(queued.notify_channel, "Stopped after multiple playback failures.")
                        return

                    next_item = self._take_next_locked()

            if next_item is None:
                return
            queued, generation = next_item

    async def _begin_playback_locked(
        self,
        voice_channel: discord.VoiceChannel | discord.StageChannel,
        track: Track,
    ) -> None:
        """Connect or move the voice client and start FFmpeg playback. Lock must be held."""
        start = time.perf_counter()
        try:
            if self.voice_client is None or not self.voice_client.is_connected():
                self.voice_client = await voice_channel.connect()
            elif self.voice_client.channel != voice_channel:
                await self.voice_client.move_to(voice_channel)

            source = discord.FFmpegPCMAudio(track.stream_url, **FFMPEG_OPTIONS)
            self._playback_generation += 1
            generation = self._playback_generation
            self.voice_client.play(
                source,
                after=lambda error: asyncio.run_coroutine_threadsafe(self._after_track(error, generation), self.loop),
            )
        except Exception as exc:
            self.current = None
            logging.warning("Could not start playback in guild %s: %s", self.guild_id, exc)

            if self.voice_client is not None and self.voice_client.is_connected():
                await self.voice_client.disconnect()
            self.voice_client = None

            raise PlaybackStartError(
                "Could not join voice or start playback. Check bot voice permissions and FFmpeg."
            ) from exc

        self.current = track
        self._playback_failures = 0
        logging.info(
            "Started playback in guild %s for %r in %.2fs",
            self.guild_id,
            track.title,
            time.perf_counter() - start,
        )

    async def _resolve_queued_track(self, queued: QueuedTrack) -> Track:
        if queued.track.stream_url:
            return Track(
                title=queued.track.title,
                webpage_url=queued.track.webpage_url,
                stream_url=queued.track.stream_url,
            )

        return await resolve_track(queued.track.webpage_url)

    async def _notify(self, channel: discord.abc.Messageable | None, message: str) -> None:
        if channel is None:
            return

        try:
            await channel.send(message[:DISCORD_MESSAGE_LIMIT])
        except Exception as exc:
            logging.warning("Could not send playback notification in guild %s: %s", self.guild_id, exc)

    async def _after_track(self, error: Exception | None, generation: int) -> None:
        if error:
            logging.warning("Playback error in guild %s: %s", self.guild_id, error)

        async with self.lock:
            if generation != self._playback_generation:
                return

            if self._stop_requested:
                self._stop_requested = False
                return

            next_item = self._take_next_locked()

        if next_item is None:
            return

        queued, next_generation = next_item
        await self._drive_playback(queued, next_generation, raise_on_error=False)


class GuildPlayerRegistry:
    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self._players: dict[int, GuildPlayer] = {}

    def for_guild(self, guild_id: int) -> GuildPlayer:
        if guild_id not in self._players:
            self._players[guild_id] = GuildPlayer(guild_id, self.loop)
        return self._players[guild_id]

    def get(self, guild_id: int) -> GuildPlayer | None:
        """Peek at an existing player without creating one."""
        return self._players.get(guild_id)
