from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import yt_dlp


MAX_QUERY_LENGTH = 200


class TrackLookupError(Exception):
    pass


@dataclass(frozen=True)
class Track:
    title: str
    webpage_url: str
    stream_url: str


def _is_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _extract(query: str) -> Track:
    ydl_query = query if _is_url(query) else f"ytsearch1:{query}"
    options: dict[str, Any] = {
        "format": "bestaudio/best",
        "quiet": True,
        "default_search": "ytsearch1",
        "noplaylist": True,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(ydl_query, download=False)

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
        return await asyncio.to_thread(_extract, query)
    except TrackLookupError:
        raise
    except yt_dlp.utils.DownloadError as exc:
        raise TrackLookupError(f"Could not resolve track: {exc}") from exc
