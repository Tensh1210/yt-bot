# Phase 2 - Control Commands

## Goal

Add the MVP control surface on top of Phase 1 playback:

- Prefix and slash commands for `pause`, `resume`, `skip`, `stop`, and `queue`.
- Keep all queue and playback state changes inside `GuildPlayer`.
- Preserve automatic next-track playback after `skip`.
- Ensure `stop` clears queue, stops playback, and disconnects without starting another track.

## Acceptance Checklist

- `pause` pauses the active track and returns a readable message if nothing is playing.
- `resume` resumes a paused track and returns a readable message if nothing is paused.
- `skip` stops the current track and starts the next queued track when available.
- `stop` clears the queue and disconnects from voice.
- `queue` shows the current track and up to the next 10 queued tracks.
- Prefix and slash command behavior match.
