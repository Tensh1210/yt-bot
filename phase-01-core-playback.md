# Phase 1 - Core Playback

## Goal

Build the minimal working Discord music bot path:

- Start bot from environment config.
- Support prefix `!play <query>` and slash `/play <query>`.
- Accept YouTube URL or keyword search.
- Resolve audio with `yt-dlp` using `ytsearch1` for keywords.
- Join the command user's voice channel.
- Stream audio through FFmpeg without downloading media files.
- Keep one in-memory player/queue per guild.
- Auto-start the next queued track when the current track ends or errors.

## Out Of Scope

- `pause`, `resume`, `skip`, `stop`, `queue` commands.
- Embed UI, now-playing progress, loop/shuffle.
- Persistent queue/history.
- Production hosting setup beyond Docker scaffold.

## Acceptance Checklist

- Bot logs in using `DISCORD_TOKEN`.
- Prefix command `!play never gonna give you up` resolves and starts playback.
- Slash command `/play query:<keyword>` resolves and starts playback.
- A second `play` while audio is active is queued.
- Playback end triggers the next queued item.
- Empty queries and users outside a voice channel return readable errors.
