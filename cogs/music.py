from __future__ import annotations

import asyncio

import discord
from discord import app_commands
from discord.ext import commands

from core.player import GuildPlayerRegistry
from core.ytdlp_source import TrackLookupError, resolve_track


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
        position = await player.enqueue(track, voice.channel)

        if position == 0:
            return f"Playing now: {track.title}"
        return f"Queued #{position}: {track.title}"

    @commands.command(name="play")
    async def prefix_play(self, ctx: commands.Context, *, query: str = "") -> None:
        message = await self._play(ctx, query)
        await ctx.reply(message, mention_author=False)

    @app_commands.command(name="play", description="Play a YouTube URL or keyword search result.")
    @app_commands.describe(query="YouTube URL or search keywords")
    async def slash_play(self, interaction: discord.Interaction, query: str) -> None:
        await interaction.response.defer()
        message = await self._play(interaction, query)
        await interaction.followup.send(message)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Music(bot))
