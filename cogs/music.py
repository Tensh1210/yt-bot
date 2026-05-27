from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

from core.player import GuildPlayerRegistry, PlaybackStartError
from core.ytdlp_source import TrackLookupError, resolve_track


GENERIC_ERROR_MESSAGE = "Something went wrong while handling that music command."


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

        try:
            track = await resolve_track(query)
        except TrackLookupError as exc:
            return str(exc)

        player = self.players.for_guild(guild.id)
        notify_channel = getattr(interaction_or_context, "channel", None)
        try:
            position = await player.enqueue(track, voice.channel, notify_channel)
        except PlaybackStartError as exc:
            return str(exc)

        if position == 0:
            return f"Playing now: {track.title}"
        return f"Queued #{position}: {track.title}"

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
        if action == "queue":
            return await player.queue_summary()

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

    @commands.command(name="stop")
    async def prefix_stop(self, ctx: commands.Context) -> None:
        await ctx.reply(await self._control(ctx, "stop"), mention_author=False)

    @commands.command(name="queue")
    async def prefix_queue(self, ctx: commands.Context) -> None:
        await ctx.reply(await self._control(ctx, "queue"), mention_author=False)

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

    @app_commands.command(name="stop", description="Stop playback and clear the queue.")
    async def slash_stop(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(await self._control(interaction, "stop"))

    @app_commands.command(name="queue", description="Show the current queue.")
    async def slash_queue(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(await self._control(interaction, "queue"))

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
