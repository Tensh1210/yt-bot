from __future__ import annotations

import pytest

from core.ytdlp_source import (
    MAX_ERROR_LENGTH,
    _clean_error_message,
    _entry_to_track_request,
    is_playlist_url,
)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.youtube.com/playlist?list=PL123", True),
        ("https://music.youtube.com/playlist?list=PL123", True),
        ("https://youtube.com/playlist?list=PL123", True),
        # A list= parameter without a specific video still means the playlist.
        ("https://www.youtube.com/watch?list=PL123", True),
        # URLs pointing at a specific video play that single video even when
        # a list= parameter is present.
        ("https://www.youtube.com/watch?v=abc123&list=PL123", False),
        ("https://youtu.be/abc123?list=PL123", False),
        ("https://www.youtube.com/watch?v=abc123", False),
        ("https://example.com/playlist?list=PL123", False),
        # A /playlist path counts even without list=; yt-dlp then reports a
        # clean playlist error instead of the URL being searched as keywords.
        ("https://www.youtube.com/playlist", True),
        ("not a url at all", False),
        ("", False),
    ],
)
def test_is_playlist_url(url, expected):
    assert is_playlist_url(url) is expected


def test_clean_error_message_strips_error_prefix():
    assert _clean_error_message(Exception("ERROR: video unavailable")) == "video unavailable"


def test_clean_error_message_empty_falls_back():
    assert _clean_error_message(Exception("")) == "Unknown extractor error."


def test_clean_error_message_truncates_long_text():
    message = _clean_error_message(Exception("x" * (MAX_ERROR_LENGTH + 50)))
    assert len(message) <= MAX_ERROR_LENGTH + 3
    assert message.endswith("...")


def test_entry_with_webpage_url_used_directly():
    request = _entry_to_track_request({"title": "Song", "webpage_url": "https://www.youtube.com/watch?v=abc"})
    assert request is not None
    assert request.title == "Song"
    assert request.webpage_url == "https://www.youtube.com/watch?v=abc"
    assert request.stream_url is None


def test_entry_with_bare_video_id_in_url_field():
    request = _entry_to_track_request({"title": "Song", "url": "abc123"})
    assert request is not None
    assert request.webpage_url == "https://www.youtube.com/watch?v=abc123"


def test_entry_with_id_only():
    request = _entry_to_track_request({"id": "abc123"})
    assert request is not None
    assert request.title == "Unknown title"
    assert request.webpage_url == "https://www.youtube.com/watch?v=abc123"


def test_entry_without_any_url_is_dropped():
    assert _entry_to_track_request({"title": "Song"}) is None
