from __future__ import annotations

import asyncio
import logging
import os
import random

import discord
from discord import app_commands
from discord.ext import commands

from core.player import GuildPlayer, GuildPlayerRegistry, PlaybackStartError, QueueFullError
from core.ytdlp_source import TrackLookupError, is_playlist_url, resolve_playlist, resolve_track


GENERIC_ERROR_MESSAGE = "Something went wrong while handling that music command."


def _playlist_shuffle_enabled() -> bool:
    return os.getenv("PLAYLIST_SHUFFLE", "1").strip() == "1"


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.players = GuildPlayerRegistry(asyncio.get_running_loop())

    async def _play(self, interaction_or_context: discord.Interaction | commands.Context, query: str) -> str:
        query = query.strip()
        if not query:
            return "Query cannot be empty."

        guild = interaction_or_context.guild
        if guild is None:
            return "This command only works in a server."

        user = interaction_or_context.user if isinstance(interaction_or_context, discord.Interaction) else interaction_or_context.author
        voice = getattr(user, "voice", None)
        if voice is None or voice.channel is None:
            return "Join a voice channel first."

        player = self.players.for_guild(guild.id)
        notify_channel = getattr(interaction_or_context, "channel", None)

        if is_playlist_url(query):
            return await self._play_playlist(query, player, voice.channel, notify_channel)

        try:
            track = await resolve_track(query)
        except TrackLookupError as exc:
            return str(exc)

        try:
            position = await player.enqueue(track, voice.channel, notify_channel)
        except (PlaybackStartError, QueueFullError) as exc:
            return str(exc)

        if position == 0:
            return f"Playing now: {track.title}"
        return f"Queued #{position}: {track.title}"

    async def _play_playlist(
        self,
        query: str,
        player: GuildPlayer,
        voice_channel: discord.VoiceChannel | discord.StageChannel,
        notify_channel: discord.abc.Messageable | None,
    ) -> str:
        try:
            playlist = await resolve_playlist(query)
        except TrackLookupError as exc:
            return str(exc)

        tracks = list(playlist.tracks)
        shuffled = _playlist_shuffle_enabled()
        if shuffled:
            random.shuffle(tracks)

        try:
            count = await player.enqueue_many(tracks, voice_channel, notify_channel)
        except (PlaybackStartError, QueueFullError) as exc:
            return str(exc)

        shuffle_note = ", shuffled" if shuffled else ""
        skipped = playlist.truncated or count < len(tracks)
        now = player.current

        if now:
            remaining = count - 1
            msg = f"Playing now: {now.title}\nQueued playlist: {playlist.title} ({remaining} more{shuffle_note})."
        else:
            msg = f"Queued playlist: {playlist.title} ({count} tracks{shuffle_note})."

        if skipped:
            msg += " Extra tracks were skipped."
        return msg

    def _player_for(self, interaction_or_context: discord.Interaction | commands.Context):
        guild = interaction_or_context.guild
        if guild is None:
            return None
        return self.players.for_guild(guild.id)

    async def _control(self, interaction_or_context: discord.Interaction | commands.Context, action: str) -> str:
        player = self._player_for(interaction_or_context)
        if player is None:
            return "This command only works in a server."

        if action == "pause":
            return await player.pause()
        if action == "resume":
            return await player.resume()
        if action == "skip":
            return await player.skip()
        if action == "stop":
            return await player.stop()
        if action == "skipplaylist":
            return await player.skip_playlist()
        if action == "queue":
            return await player.queue_summary()
        if action == "nowplaying":
            return await player.now_playing()

        return "Unknown command."

    @commands.command(name="play")
    async def prefix_play(self, ctx: commands.Context, *, query: str = "") -> None:
        message = await self._play(ctx, query)
        await ctx.reply(message, mention_author=False)

    @commands.command(name="pause")
    async def prefix_pause(self, ctx: commands.Context) -> None:
        await ctx.reply(await self._control(ctx, "pause"), mention_author=False)

    @commands.command(name="resume")
    async def prefix_resume(self, ctx: commands.Context) -> None:
        await ctx.reply(await self._control(ctx, "resume"), mention_author=False)

    @commands.command(name="skip")
    async def prefix_skip(self, ctx: commands.Context) -> None:
        await ctx.reply(await self._control(ctx, "skip"), mention_author=False)

    @commands.command(name="skipplaylist", aliases=["skipp"])
    async def prefix_skipplaylist(self, ctx: commands.Context) -> None:
        await ctx.reply(await self._control(ctx, "skipplaylist"), mention_author=False)

    @commands.command(name="stop")
    async def prefix_stop(self, ctx: commands.Context) -> None:
        await ctx.reply(await self._control(ctx, "stop"), mention_author=False)

    @commands.command(name="queue")
    async def prefix_queue(self, ctx: commands.Context) -> None:
        await ctx.reply(await self._control(ctx, "queue"), mention_author=False)

    @commands.command(name="nowplaying", aliases=["np"])
    async def prefix_nowplaying(self, ctx: commands.Context) -> None:
        await ctx.reply(await self._control(ctx, "nowplaying"), mention_author=False)

    @app_commands.command(name="play", description="Play a YouTube URL or keyword search result.")
    @app_commands.describe(query="YouTube URL or search keywords")
    async def slash_play(self, interaction: discord.Interaction, query: str) -> None:
        await interaction.response.defer()
        message = await self._play(interaction, query)
        await interaction.followup.send(message)

    @app_commands.command(name="pause", description="Pause the current track.")
    async def slash_pause(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(await self._control(interaction, "pause"))

    @app_commands.command(name="resume", description="Resume the paused track.")
    async def slash_resume(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(await self._control(interaction, "resume"))

    @app_commands.command(name="skip", description="Skip the current track.")
    async def slash_skip(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(await self._control(interaction, "skip"))

    @app_commands.command(name="skipplaylist", description="Skip the current playlist and remove its tracks from queue.")
    async def slash_skipplaylist(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(await self._control(interaction, "skipplaylist"))

    @app_commands.command(name="stop", description="Stop playback and clear the queue.")
    async def slash_stop(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(await self._control(interaction, "stop"))

    @app_commands.command(name="queue", description="Show the current queue.")
    async def slash_queue(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(await self._control(interaction, "queue"))

    @app_commands.command(name="nowplaying", description="Show the current track.")
    async def slash_nowplaying(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(await self._control(interaction, "nowplaying"))

    @prefix_play.error
    async def prefix_play_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.reply("Usage: `!play <YouTube URL or keywords>`", mention_author=False)
            return
        raise error

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.CommandInvokeError) and error.original:
            error = error.original

        logging.exception("Music prefix command failed", exc_info=error)
        await ctx.reply(GENERIC_ERROR_MESSAGE, mention_author=False)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        logging.exception("Music slash command failed", exc_info=error)

        if interaction.response.is_done():
            await interaction.followup.send(GENERIC_ERROR_MESSAGE)
        else:
            await interaction.response.send_message(GENERIC_ERROR_MESSAGE)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Music(bot))
