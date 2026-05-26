# Phase 4 - Packaging and Deploy

## Goal

Make the MVP easy to run locally, run in Docker, and smoke test in a real private Discord server.

## Scope

- Add deployment-oriented docs.
- Add Docker ignore rules and a minimal Compose file.
- Keep secrets out of the image and repository.
- Support optional guild-scoped slash command sync for fast testing.
- Document required Discord Developer Portal settings.

## Acceptance Checklist

- `.env.example` documents every supported environment variable.
- `docker compose up --build` can start the bot when `.env` contains a valid token.
- Docker build context excludes `.git`, caches, virtualenvs, and local `.env`.
- README explains local setup, Docker setup, Discord intents, and smoke test steps.
- Optional guild sync is available through `DISCORD_GUILD_ID`.
