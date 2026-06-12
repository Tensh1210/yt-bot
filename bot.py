import asyncio
import logging

import discord
from discord.ext import commands
from dotenv import load_dotenv

from core.config import get_config, init_config


class MusicBot(commands.Bot):
    async def setup_hook(self) -> None:
        await self.load_extension("cogs.music")

        config = get_config()
        if config.sync_slash_commands:
            if config.discord_guild_id is not None:
                guild = discord.Object(id=config.discord_guild_id)
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
            else:
                await self.tree.sync()


async def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    # Parse all environment variables up front so bad values stop the bot here.
    config = init_config()

    intents = discord.Intents.default()
    intents.guilds = True
    intents.voice_states = True
    intents.message_content = True

    bot = MusicBot(command_prefix=config.command_prefix, intents=intents)

    @bot.event
    async def on_ready() -> None:
        logging.info("Logged in as %s (%s)", bot.user, bot.user.id if bot.user else "unknown")

    await bot.start(config.discord_token)


if __name__ == "__main__":
    asyncio.run(main())
