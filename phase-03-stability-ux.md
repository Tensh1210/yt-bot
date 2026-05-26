# Phase 3 - Stability and UX

## Goal

Harden the MVP command flow so common runtime failures produce clear messages and do not leave stale voice or queue state.

## Scope

- Handle Discord voice connect/move/playback start failures.
- Keep queue state consistent when playback startup fails.
- Make `stop` idempotent and prevent stale playback callbacks from restarting the queue.
- Shorten noisy `yt-dlp` errors for Discord messages.
- Cap queue output to a safe Discord message length.

## Acceptance Checklist

- Failed voice connection removes the attempted current track and returns a readable error.
- Failed FFmpeg playback startup removes the attempted current track and returns a readable error.
- `stop` works when disconnected, idle, playing, or paused.
- Playback callback after `stop` does not start another queued track.
- Long `yt-dlp` errors are truncated to a readable message.
- `queue` output stays under Discord's 2000-character message limit.
