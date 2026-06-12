from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlparse

import yt_dlp
from ytmusicapi import YTMusic

from core.config import get_config


MAX_QUERY_LENGTH = 200
MAX_ERROR_LENGTH = 300
LOOKUP_TIMEOUT_SECONDS = 15
# Resolved tracks are cached so repeated requests and prefetched queue heads
# skip the multi-second yt-dlp lookup. The TTL stays far below the ~6h stream
# URL lifetime so a cached URL is always still playable.
RESOLVE_CACHE_TTL_SECONDS = 2 * 60 * 60
RESOLVE_CACHE_MAX_ENTRIES = 200
YTMUSIC_WATCH_URL = "https://music.youtube.com/watch?v="
YOUTUBE_WATCH_URL = "https://www.youtube.com/watch?v="
AUDIO_FORMAT = "bestaudio[abr<=128]/bestaudio/best"


class TrackLookupError(Exception):
    pass


@dataclass(frozen=True)
class Track:
    title: str
    webpage_url: str
    stream_url: str


@dataclass(frozen=True)
class TrackRequest:
    title: str
    webpage_url: str
    stream_url: str | None = None


@dataclass(frozen=True)
class PlaylistLookup:
    title: str
    tracks: list[TrackRequest]
    truncated: bool


# Only touched from the event loop (resolve_track), so no lock is needed.
_resolve_cache: OrderedDict[str, tuple[Track, float]] = OrderedDict()


def _resolve_cache_get(query: str) -> Track | None:
    entry = _resolve_cache.get(query)
    if entry is None:
        return None
    track, expires_at = entry
    if time.monotonic() >= expires_at:
        del _resolve_cache[query]
        return None
    _resolve_cache.move_to_end(query)
    return track


def _resolve_cache_put(query: str, track: Track) -> None:
    expires_at = time.monotonic() + RESOLVE_CACHE_TTL_SECONDS
    _resolve_cache[query] = (track, expires_at)
    _resolve_cache.move_to_end(query)
    # Also key by the canonical video URL: a track queued after a keyword
    # search is re-resolved by webpage_url right before playback, and this
    # second key turns that lookup into a cache hit.
    if track.webpage_url != query:
        _resolve_cache[track.webpage_url] = (track, expires_at)
        _resolve_cache.move_to_end(track.webpage_url)
    while len(_resolve_cache) > RESOLVE_CACHE_MAX_ENTRIES:
        _resolve_cache.popitem(last=False)


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


def is_playlist_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False

    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host.removeprefix("www.")

    if host not in {"youtube.com", "music.youtube.com", "youtu.be"}:
        return False

    if parsed.path.rstrip("/") == "/playlist":
        return True

    query = parse_qs(parsed.query)
    if not query.get("list", [""])[0]:
        return False

    # URLs that point at a specific video (watch?v=... or youtu.be/<id>) play
    # that single video even when a list= parameter is present; queueing the
    # whole playlist requires an explicit /playlist URL.
    if query.get("v", [""])[0]:
        return False
    if host == "youtu.be" and parsed.path.strip("/"):
        return False

    return True


# YTMusic session setup is slow, so one shared instance serves all searches.
# The lock only guards creation; searches run concurrently on the shared session.
_ytmusic_lock = threading.Lock()
_ytmusic: YTMusic | None = None


def _get_ytmusic() -> YTMusic:
    global _ytmusic
    with _ytmusic_lock:
        if _ytmusic is None:
            _ytmusic = YTMusic()
        return _ytmusic


def _resolve_ytmusic_query(query: str) -> str | None:
    start = time.perf_counter()
    try:
        results = _get_ytmusic().search(query, filter="songs", limit=1)
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
    elif get_config().search_provider == "ytmusic":
        ydl_query = _resolve_ytmusic_query(query) or f"ytsearch1:{query}"
    else:
        ydl_query = f"ytsearch1:{query}"

    options: dict[str, Any] = {
        "format": AUDIO_FORMAT,
        "quiet": True,
        "default_search": "ytsearch1",
        "noplaylist": True,
        # yt-dlp expects "component:source" strings; a {"ejs": "github"} dict
        # is read as just "ejs" and the JS challenge solver silently stays off.
        "remote_components": ["ejs:github"],
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


def _entry_to_track_request(entry: dict[str, Any]) -> TrackRequest | None:
    title = entry.get("title") or "Unknown title"
    webpage_url = entry.get("webpage_url")
    entry_url = entry.get("url")
    video_id = entry.get("id")

    if not webpage_url and isinstance(entry_url, str):
        webpage_url = entry_url if _is_url(entry_url) else f"{YOUTUBE_WATCH_URL}{entry_url}"

    if not webpage_url and video_id:
        webpage_url = f"{YOUTUBE_WATCH_URL}{video_id}"

    if not webpage_url:
        return None

    return TrackRequest(title=title, webpage_url=webpage_url)


def _extract_playlist(query: str) -> PlaylistLookup:
    if not is_playlist_url(query):
        raise TrackLookupError("This URL does not look like a supported YouTube playlist.")

    max_items = get_config().max_playlist_items
    options: dict[str, Any] = {
        "extract_flat": True,
        "ignoreerrors": True,
        "playlistend": max_items + 1,
        "quiet": True,
        "skip_download": True,
        # yt-dlp expects "component:source" strings; a {"ejs": "github"} dict
        # is read as just "ejs" and the JS challenge solver silently stays off.
        "remote_components": ["ejs:github"],
    }

    start = time.perf_counter()
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(query, download=False)
    logging.info("yt-dlp loaded playlist metadata for %r in %.2fs", query, time.perf_counter() - start)

    if not info:
        raise TrackLookupError("Could not load this playlist.")

    entries = [entry for entry in info.get("entries", []) if entry]
    tracks = [track for entry in entries if (track := _entry_to_track_request(entry))]
    if not tracks:
        raise TrackLookupError("No playable tracks found in this playlist.")

    truncated = len(tracks) > max_items
    return PlaylistLookup(
        title=info.get("title") or "Playlist",
        tracks=tracks[:max_items],
        truncated=truncated,
    )


async def resolve_track(query: str) -> Track:
    query = query.strip()
    if not query:
        raise TrackLookupError("Query cannot be empty.")
    if len(query) > MAX_QUERY_LENGTH:
        raise TrackLookupError(f"Query is too long. Keep it under {MAX_QUERY_LENGTH} characters.")

    cached = _resolve_cache_get(query)
    if cached is not None:
        logging.info("Resolve cache hit for %r", query)
        return cached

    try:
        start = time.perf_counter()
        track = await asyncio.wait_for(asyncio.to_thread(_extract, query), timeout=LOOKUP_TIMEOUT_SECONDS)
        logging.info("Track lookup for %r completed in %.2fs", query, time.perf_counter() - start)
        _resolve_cache_put(query, track)
        return track
    except asyncio.TimeoutError as exc:
        raise TrackLookupError(f"Track lookup timed out after {LOOKUP_TIMEOUT_SECONDS} seconds. Try again later.") from exc
    except TrackLookupError:
        raise
    except yt_dlp.utils.DownloadError as exc:
        raise TrackLookupError(f"Could not resolve track: {_clean_error_message(exc)}") from exc
    except Exception as exc:
        raise TrackLookupError(f"Unexpected extractor error: {_clean_error_message(exc)}") from exc


async def resolve_playlist(query: str) -> PlaylistLookup:
    query = query.strip()
    if not query:
        raise TrackLookupError("Playlist URL cannot be empty.")

    timeout_seconds = get_config().playlist_lookup_timeout_seconds
    try:
        start = time.perf_counter()
        playlist = await asyncio.wait_for(asyncio.to_thread(_extract_playlist, query), timeout=timeout_seconds)
        logging.info(
            "Playlist lookup for %r loaded %s tracks in %.2fs",
            query,
            len(playlist.tracks),
            time.perf_counter() - start,
        )
        return playlist
    except asyncio.TimeoutError as exc:
        raise TrackLookupError(f"Playlist lookup timed out after {timeout_seconds} seconds. Try again later.") from exc
    except TrackLookupError:
        raise
    except yt_dlp.utils.DownloadError as exc:
        raise TrackLookupError(f"Could not load playlist: {_clean_error_message(exc)}") from exc
    except Exception as exc:
        raise TrackLookupError(f"Unexpected playlist error: {_clean_error_message(exc)}") from exc
