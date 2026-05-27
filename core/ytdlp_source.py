from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import yt_dlp
from ytmusicapi import YTMusic


MAX_QUERY_LENGTH = 200
MAX_ERROR_LENGTH = 300
LOOKUP_TIMEOUT_SECONDS = 15
YTMUSIC_WATCH_URL = "https://music.youtube.com/watch?v="
AUDIO_FORMAT = "bestaudio[abr<=128]/bestaudio/best"


class TrackLookupError(Exception):
    pass


@dataclass(frozen=True)
class Track:
    title: str
    webpage_url: str
    stream_url: str


def _clean_error_message(error: Exception) -> str:
    message = str(error).strip()
    if not message:
        return "Unknown extractor error."

    if message.startswith("ERROR: "):
        message = message.removeprefix("ERROR: ").strip()

    if len(message) > MAX_ERROR_LENGTH:
        message = f"{message[:MAX_ERROR_LENGTH].rstrip()}..."

    return message


def _is_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _resolve_ytmusic_query(query: str) -> str | None:
    start = time.perf_counter()
    try:
        ytmusic = YTMusic()
        results = ytmusic.search(query, filter="songs", limit=1)
    except Exception as exc:
        logging.warning("YouTube Music search failed for %r: %s", query, exc)
        return None
    finally:
        logging.info("YouTube Music search for %r completed in %.2fs", query, time.perf_counter() - start)

    if not results:
        return None

    video_id = results[0].get("videoId")
    if not video_id:
        return None

    logging.info("YouTube Music matched %r to video id %s", query, video_id)
    return f"{YTMUSIC_WATCH_URL}{video_id}"


def _extract(query: str) -> Track:
    if _is_url(query):
        ydl_query = query
    elif os.getenv("SEARCH_PROVIDER", "ytmusic").lower() == "ytmusic":
        ydl_query = _resolve_ytmusic_query(query) or f"ytsearch1:{query}"
    else:
        ydl_query = f"ytsearch1:{query}"

    options: dict[str, Any] = {
        "format": AUDIO_FORMAT,
        "quiet": True,
        "default_search": "ytsearch1",
        "noplaylist": True,
    }

    start = time.perf_counter()
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(ydl_query, download=False)
    logging.info("yt-dlp resolved %r in %.2fs", ydl_query, time.perf_counter() - start)

    if not info:
        raise TrackLookupError("No match found for keyword.")

    if "entries" in info:
        entries = [entry for entry in info.get("entries", []) if entry]
        if not entries:
            raise TrackLookupError("No match found for keyword.")
        info = entries[0]

    stream_url = info.get("url")
    title = info.get("title") or "Unknown title"
    webpage_url = info.get("webpage_url") or info.get("original_url") or query

    if not stream_url:
        raise TrackLookupError("Could not resolve an audio stream for this query.")

    return Track(title=title, webpage_url=webpage_url, stream_url=stream_url)


async def resolve_track(query: str) -> Track:
    query = query.strip()
    if not query:
        raise TrackLookupError("Query cannot be empty.")
    if len(query) > MAX_QUERY_LENGTH:
        raise TrackLookupError(f"Query is too long. Keep it under {MAX_QUERY_LENGTH} characters.")

    try:
        start = time.perf_counter()
        track = await asyncio.wait_for(asyncio.to_thread(_extract, query), timeout=LOOKUP_TIMEOUT_SECONDS)
        logging.info("Track lookup for %r completed in %.2fs", query, time.perf_counter() - start)
        return track
    except asyncio.TimeoutError as exc:
        raise TrackLookupError(f"Track lookup timed out after {LOOKUP_TIMEOUT_SECONDS} seconds. Try again later.") from exc
    except TrackLookupError:
        raise
    except yt_dlp.utils.DownloadError as exc:
        raise TrackLookupError(f"Could not resolve track: {_clean_error_message(exc)}") from exc
    except Exception as exc:
        raise TrackLookupError(f"Unexpected extractor error: {_clean_error_message(exc)}") from exc
