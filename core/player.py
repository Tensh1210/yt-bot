from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass

import discord

from core.ytdlp_source import Track


FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


@dataclass
class QueuedTrack:
    track: Track
    voice_channel: discord.VoiceChannel | discord.StageChannel


class GuildPlayer:
    def __init__(self, guild_id: int, loop: asyncio.AbstractEventLoop) -> None:
        self.guild_id = guild_id
        self.loop = loop
        self.queue: deque[QueuedTrack] = deque()
        self.lock = asyncio.Lock()
        self.voice_client: discord.VoiceClient | None = None
        self.current: Track | None = None

    async def enqueue(self, track: Track, voice_channel: discord.VoiceChannel | discord.StageChannel) -> int:
        async with self.lock:
            self.queue.append(QueuedTrack(track=track, voice_channel=voice_channel))
            position = len(self.queue)

            if self.voice_client is None or not self.voice_client.is_playing():
                await self._play_next_locked()
                return 0

            return position

    async def _play_next_locked(self) -> None:
        if not self.queue:
            self.current = None
            return

        queued = self.queue.popleft()
        self.current = queued.track

        if self.voice_client is None or not self.voice_client.is_connected():
            self.voice_client = await queued.voice_channel.connect()
        elif self.voice_client.channel != queued.voice_channel:
            await self.voice_client.move_to(queued.voice_channel)

        source = discord.FFmpegPCMAudio(queued.track.stream_url, **FFMPEG_OPTIONS)
        self.voice_client.play(
            source,
            after=lambda error: asyncio.run_coroutine_threadsafe(self._after_track(error), self.loop),
        )

    async def _after_track(self, error: Exception | None) -> None:
        if error:
            logging.warning("Playback error in guild %s: %s", self.guild_id, error)

        async with self.lock:
            await self._play_next_locked()


class GuildPlayerRegistry:
    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self._players: dict[int, GuildPlayer] = {}

    def for_guild(self, guild_id: int) -> GuildPlayer:
        if guild_id not in self._players:
            self._players[guild_id] = GuildPlayer(guild_id, self.loop)
        return self._players[guild_id]
