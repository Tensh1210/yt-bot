# Discord Music Bot

Private-server Discord music bot MVP using `discord.py`, `yt-dlp`, and FFmpeg.

## Features

- Prefix and slash commands.
- YouTube URL and keyword search playback, with YouTube Music search preferred.
- YouTube playlist support: `!play <playlist-url>` queues up to 200 tracks (shuffled by default).
- Per-server in-memory queue (up to 200 tracks).
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
SEARCH_PROVIDER=ytdlp
MAX_QUEUE_SIZE=200
MAX_PLAYLIST_ITEMS=200
PLAYLIST_LOOKUP_TIMEOUT_SECONDS=30
PLAYLIST_SHUFFLE=1
IDLE_DISCONNECT_SECONDS=300
YTDLP_AUTO_UPDATE=1
```

Use `DISCORD_GUILD_ID` during testing if you want slash commands to sync immediately to one server. Leave it empty for global slash command sync.
Set `SEARCH_PROVIDER=ytmusic` to use YouTube Music search instead of direct YouTube search.
Set `PLAYLIST_SHUFFLE=0` to disable playlist shuffle and preserve the original playlist order.
`IDLE_DISCONNECT_SECONDS` controls how long the bot stays in voice after the queue empties (default 300, set 0 to never auto-leave). The bot also leaves immediately when every human listener exits its voice channel.
`MAX_PLAYLIST_ITEMS` caps how many tracks are imported from one playlist (default 200); `MAX_QUEUE_SIZE` caps the total queue size across all enqueued tracks.
`YTDLP_AUTO_UPDATE=1` (Docker only) upgrades yt-dlp to the latest release on every container start, since YouTube changes break old yt-dlp versions quickly. Set 0 to skip.
All environment variables are validated once at startup; the bot refuses to start with a clear error if any value is invalid.

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
- `!play https://www.youtube.com/playlist?list=<playlist-id>` — verify playlist title and track count in response.

If slash commands do not appear quickly, set `DISCORD_GUILD_ID` to the server ID and restart the bot.
