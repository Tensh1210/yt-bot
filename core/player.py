from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass

import discord

from core.ytdlp_source import Track


DISCORD_MESSAGE_LIMIT = 2000

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


@dataclass
class QueuedTrack:
    track: Track
    voice_channel: discord.VoiceChannel | discord.StageChannel


class PlaybackStartError(Exception):
    pass


class GuildPlayer:
    def __init__(self, guild_id: int, loop: asyncio.AbstractEventLoop) -> None:
        self.guild_id = guild_id
        self.loop = loop
        self.queue: deque[QueuedTrack] = deque()
        self.lock = asyncio.Lock()
        self.voice_client: discord.VoiceClient | None = None
        self.current: Track | None = None
        self._stop_requested = False

    async def enqueue(self, track: Track, voice_channel: discord.VoiceChannel | discord.StageChannel) -> int:
        async with self.lock:
            self.queue.append(QueuedTrack(track=track, voice_channel=voice_channel))
            position = len(self.queue)

            if self.voice_client is None or (not self.voice_client.is_playing() and not self.voice_client.is_paused()):
                try:
                    await self._play_next_locked()
                except PlaybackStartError:
                    raise
                return 0

            return position

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

    async def stop(self) -> str:
        async with self.lock:
            self.queue.clear()
            self.current = None
            self._stop_requested = True

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
                lines.append("Up next:")
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

    async def _play_next_locked(self) -> None:
        if not self.queue:
            self.current = None
            return

        self._stop_requested = False
        queued = self.queue.popleft()
        self.current = queued.track

        try:
            if self.voice_client is None or not self.voice_client.is_connected():
                self.voice_client = await queued.voice_channel.connect()
            elif self.voice_client.channel != queued.voice_channel:
                await self.voice_client.move_to(queued.voice_channel)

            source = discord.FFmpegPCMAudio(queued.track.stream_url, **FFMPEG_OPTIONS)
            self.voice_client.play(
                source,
                after=lambda error: asyncio.run_coroutine_threadsafe(self._after_track(error), self.loop),
            )
        except Exception as exc:
            self.current = None
            logging.warning("Could not start playback in guild %s: %s", self.guild_id, exc)

            if self.voice_client is not None and self.voice_client.is_connected():
                await self.voice_client.disconnect()
            self.voice_client = None

            raise PlaybackStartError("Could not join voice or start playback. Check bot voice permissions and FFmpeg.") from exc

    async def _after_track(self, error: Exception | None) -> None:
        if error:
            logging.warning("Playback error in guild %s: %s", self.guild_id, error)

        async with self.lock:
            if self._stop_requested:
                self._stop_requested = False
                return

            try:
                await self._play_next_locked()
            except PlaybackStartError as exc:
                logging.warning("Could not auto-start next track in guild %s: %s", self.guild_id, exc)


class GuildPlayerRegistry:
    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self._players: dict[int, GuildPlayer] = {}

    def for_guild(self, guild_id: int) -> GuildPlayer:
        if guild_id not in self._players:
            self._players[guild_id] = GuildPlayer(guild_id, self.loop)
        return self._players[guild_id]
