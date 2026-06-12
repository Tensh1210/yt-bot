#!/bin/sh
set -e

# yt-dlp breaks quickly as YouTube changes; upgrade to the latest release on
# every container start so the pinned build version is only a fallback.
# Set YTDLP_AUTO_UPDATE=0 to skip (e.g. offline or air-gapped deployments).
if [ "${YTDLP_AUTO_UPDATE:-1}" = "1" ]; then
  pip install --no-cache-dir --upgrade yt-dlp \
    || echo "WARNING: yt-dlp upgrade failed; continuing with the bundled version." >&2
fi

exec python bot.py
