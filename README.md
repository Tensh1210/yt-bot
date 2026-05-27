# Discord Music Bot

Private-server Discord music bot MVP using `discord.py`, `yt-dlp`, and FFmpeg.

## Features

- Prefix and slash commands.
- YouTube URL playback.
- Keyword search playback, with YouTube Music search preferred and `ytsearch1` fallback.
- Per-server in-memory queue.
- `play`, `pause`, `resume`, `skip`, `stop`, `queue`, and `nowplaying`.
- Docker runtime with FFmpeg included.

## Discord Setup

Create a bot in the Discord Developer Portal, then enable these bot settings:

- `MESSAGE CONTENT INTENT` for prefix commands like `!play`.
- Server install with bot permissions for sending messages and joining/speaking in voice channels.
- OAuth2 scopes: `bot` and `applications.commands`.

Recommended bot permissions:

- `Send Messages`
- `Read Message History`
- `Connect`
- `Speak`
- `Use Voice Activity`

## Environment

Create `.env` from `.env.example`:

```env
DISCORD_TOKEN=replace-with-your-bot-token
COMMAND_PREFIX=!
SYNC_SLASH_COMMANDS=1
DISCORD_GUILD_ID=
SEARCH_PROVIDER=ytmusic
MAX_QUEUE_SIZE=50
```

Use `DISCORD_GUILD_ID` during testing if you want slash commands to sync immediately to one server. Leave it empty for global slash command sync.
Set `SEARCH_PROVIDER=ytdlp` if you want keyword search to skip YouTube Music and use direct `ytsearch1` fallback.

## Run Locally

Install Python 3.11 and FFmpeg, then run:

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python bot.py
```

## Run With Docker

```bash
docker compose up --build
```

Stop it with:

```bash
docker compose down
```

## Smoke Test

Run these in a Discord server where the bot is installed:

- Join a voice channel.
- `!play never gonna give you up`
- `/play query:lofi hip hop`
- Add a second track and verify it queues.
- `!queue`
- `!nowplaying`
- `!pause`
- `!resume`
- `!skip`
- `!stop`

If slash commands do not appear quickly, set `DISCORD_GUILD_ID` to the server ID and restart the bot.
