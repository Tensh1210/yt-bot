# Discord Music Bot - Fast MVP Plan (1-2 days)

> Updated: 2026-05-26  
> Goal: Personal/private server bot, ship fast, support both prefix and slash commands, prioritize keyword search.

---

## 1) Product Goal

- Primary use: private Discord server (small number of users).
- Priority: fastest time-to-working bot with acceptable stability.
- Command style: support both `!play` and `/play` (and equivalent for core controls).
- Required Discord intents for MVP:
  - `guilds`, `voice_states` for slash + voice operations
  - `message_content` for prefix commands (`!play`, etc.) and must be enabled in Discord Developer Portal
- Must-have in MVP:
  - Play by YouTube URL
  - Play by keyword search (important)
  - Pause, resume, skip, stop
  - Queue list

---

## 2) Scope (MVP only)

### In scope

- Join voice channel and play audio stream via `yt-dlp + FFmpeg` (no file download).
- Commands (both prefix and slash):
  - `play` (URL or keyword)
  - `pause`, `resume`, `skip`, `stop`
  - `queue`
- Per-guild in-memory queue.
- Basic error handling and user-facing messages.

### Out of scope (phase after MVP)

- Playlist bulk import
- Loop/shuffle
- Advanced embed UI/nowplaying progress bar
- Persistent DB queue/history

---

## 3) Tech Decisions

| Component | Choice | Why |
|---|---|---|
| Language | Python 3.11 | Fast to implement, familiar ecosystem |
| Discord SDK | `discord.py` 2.x | Supports slash commands + stable |
| Audio extract | `yt-dlp` | Reliable for YouTube URL + keyword |
| Playback | FFmpeg | Standard Discord voice pipeline |
| Runtime | Docker | Reproducible setup |
| State | In-memory per guild | Enough for private MVP |

---

## 4) Architecture (minimal but safe)

```text
discord-music-bot/
|-- bot.py
|-- cogs/
|   `-- music.py
|-- core/
|   |-- player.py          # GuildPlayer state (queue, current, voice client)
|   `-- ytdlp_source.py    # URL/keyword extract helpers
|-- requirements.txt
|-- .env.example
`-- Dockerfile
```

Core rule:

- `GuildPlayer` per guild (`dict[guild_id] -> GuildPlayer`).
- Every queue mutation goes through one async lock per guild.
- On track end or error, always trigger `play_next()` to avoid stuck queue.

---

## 5) Command Spec (Prefix + Slash)

All commands are available as:

- Prefix: `!play ...`, `!pause`, ...
- Slash: `/play ...`, `/pause`, ...

Behavior:

- `play <query>`:
  - If input is YouTube URL: play/add directly.
  - Else treat as keyword and resolve using `ytsearch1:<query>`.
  - If bot is idle: play now.
  - If already playing: enqueue and confirm position.
- `pause`: pause current track.
- `resume`: resume paused track.
- `skip`: stop current and auto-play next.
- `stop`: stop playback, clear queue, disconnect.
- `queue`: show current + next items (max first 10 entries).

Keyword-search requirement (important):

- Default to `ytsearch1` for speed.
- If no result, return clear message: "No match found for keyword."
- Sanitize overly long query and reject empty query.

---

## 6) Delivery Plan (1-2 days)

### Day 1 (MVP functional)

- Project bootstrap, env loading, bot startup.
- Implement voice join + play pipeline.
- Implement `play` with URL + keyword support.
- Implement `pause/resume/skip/stop/queue`.
- Add per-guild player state + lock.
- Configure and verify required Discord intents (`guilds`, `voice_states`, `message_content`).
- Local manual test pass.

### Day 2 (stabilize + deploy)

- Improve error handling and reconnect/cleanup paths.
- Add slash command sync and help text.
- Dockerize and deploy to chosen host.
- Smoke test in real Discord server.

If only 1 day available, finish Day 1 + basic Dockerfile.

---

## 7) Testing Checklist (manual, fast)

- Bot joins correct voice channel of command user.
- `play` with valid YouTube URL works.
- `play` with keyword works (at least 3 random keywords).
- Slash `play` with intentionally slow extraction does not timeout (interaction is deferred, then follow-up message sent).
- Queue order preserved when multiple `play` calls quickly.
- `skip` moves to next track without hanging.
- `stop` clears queue and disconnects.
- Commands from another guild do not affect current guild queue.
- Invalid query and removed/blocked video return readable error.

---

## 8) Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| `yt-dlp` extractor breakage | Medium | Pin tested version; update only when needed |
| FFmpeg missing on host | High | Ship Docker image with FFmpeg preinstalled |
| Queue race condition | High | Per-guild `asyncio.Lock` around queue/state ops |
| Discord interaction timeout (slash) | Medium | Defer response for long extraction |
| Hosting policy/cost changes | Medium | Verify current plan before final deploy |

---

## 9) Host Decision Guide (because Q4 = undecided)

For your priorities (fast setup, private use):

1. `Railway` if you want quickest Docker deploy UX.
2. `VPS + Docker` if you need predictable always-on behavior.
3. `Local/self-host` if this is temporary testing only.

Suggested path now: start local, then deploy to Railway if acceptable after quick trial.

---

## 10) Dependencies (pinned for stability)

```txt
discord.py==2.4.0
yt-dlp==2026.03.31
PyNaCl==1.5.0
python-dotenv==1.0.1
```

Note: keep `yt-dlp` pinned during MVP; upgrade intentionally after testing.

---

## 11) Dockerfile (MVP)

```dockerfile
FROM python:3.11-slim

RUN apt-get update \
  && apt-get install -y --no-install-recommends ffmpeg \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
CMD ["python", "bot.py"]
```

---

## 12) Immediate Next Build Prompt (for Codex CLI)

```text
Build a Discord music bot (Python + discord.py 2.x) for a private server.
Requirements:
- Support both prefix and slash commands for: play, pause, resume, skip, stop, queue
- !play / /play must accept YouTube URL OR keyword search
- For keyword use yt-dlp ytsearch1 and return clear error if no result
- Stream audio via FFmpeg (no download)
- Per-guild in-memory queue with asyncio.Lock to avoid race conditions
- Auto play next track on end/error; never leave queue stuck
- Add Dockerfile and .env.example
Keep code minimal and MVP-focused.
```
