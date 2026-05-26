import asyncio
import logging
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv


class MusicBot(commands.Bot):
    async def setup_hook(self) -> None:
        await self.load_extension("cogs.music")

        if os.getenv("SYNC_SLASH_COMMANDS", "1") == "1":
            guild_id = os.getenv("DISCORD_GUILD_ID")
            if guild_id:
                try:
                    guild = discord.Object(id=int(guild_id))
                except ValueError as exc:
                    raise RuntimeError("DISCORD_GUILD_ID must be a numeric Discord server ID") from exc

                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
            else:
                await self.tree.sync()


async def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN is required")

    intents = discord.Intents.default()
    intents.guilds = True
    intents.voice_states = True
    intents.message_content = True

    bot = MusicBot(command_prefix=os.getenv("COMMAND_PREFIX", "!"), intents=intents)

    @bot.event
    async def on_ready() -> None:
        logging.info("Logged in as %s (%s)", bot.user, bot.user.id if bot.user else "unknown")

    await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())
