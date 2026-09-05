"""Tests for YouTube special URL extraction."""

from __future__ import annotations

import unittest.mock
from types import SimpleNamespace

import requests
from markdown_this import extractor as extractor_module
from markdown_this import fetch_youtube_video
from markdown_this import fetchers as fetchers_module
from youtube_transcript_api._errors import CouldNotRetrieveTranscript

VIDEO_ID = "dQw4w9WgXcQ"
VIDEO_URL = f"https://www.youtube.com/watch?v={VIDEO_ID}"
PAGE_HTML = '<meta name="description" content="A useful video description.">'


class _OEmbedResponse:
    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict[str, str]:
        return {"title": "A YouTube video", "author_name": "Example channel"}


def _patch_oembed(response: object | None = None) -> unittest.mock._patch:
    return unittest.mock.patch(
        "markdown_this.fetchers.requests.get",
        return_value=response or _OEmbedResponse(),
    )


def test_fetch_youtube_video_extracts_channel_description_and_manual_transcript() -> None:
    transcript = [SimpleNamespace(text="First sentence"), SimpleNamespace(text="Second sentence")]
    transcript_list = unittest.mock.Mock()
    transcript_list.find_manually_created_transcript.return_value.fetch.return_value = transcript
    with (
        _patch_oembed(),
        unittest.mock.patch("markdown_this.fetchers.fetch_html", return_value=PAGE_HTML),
        unittest.mock.patch("markdown_this.fetchers.YouTubeTranscriptApi") as api,
    ):
        api.return_value.list.return_value = transcript_list
        result = fetch_youtube_video(VIDEO_URL, timeout=7)

    assert result == (
        "A YouTube video",
        "**Channel:** Example channel\n\n**Description:** A useful video description.\n\n"
        "**Transcript:**\n\n> First sentence Second sentence",
    )


def test_fetch_youtube_video_accepts_supported_url_shapes() -> None:
    urls = [
        VIDEO_URL,
        f"https://youtu.be/{VIDEO_ID}",
        f"https://www.youtube.com/embed/{VIDEO_ID}",
        f"https://m.youtube.com/shorts/{VIDEO_ID}?feature=share",
    ]
    with (
        _patch_oembed(),
        unittest.mock.patch("markdown_this.fetchers.fetch_html", return_value=""),
        unittest.mock.patch("markdown_this.fetchers._fetch_youtube_transcript", return_value=None),
    ):
        for url in urls:
            assert fetch_youtube_video(url) is not None


def test_fetch_youtube_video_rejects_non_youtube_and_invalid_urls() -> None:
    assert fetch_youtube_video("https://example.com/video") is None
    assert fetch_youtube_video("https://www.youtube.com/watch?v=too-short") is None
    assert fetch_youtube_video(f"https://www.youtube.com/watch?list=abc&x={VIDEO_ID}") is None


def test_fetch_youtube_video_returns_none_when_oembed_fails() -> None:
    with unittest.mock.patch(
        "markdown_this.fetchers.requests.get",
        side_effect=requests.RequestException("network error"),
    ):
        assert fetch_youtube_video(VIDEO_URL) is None

    response = unittest.mock.Mock()
    response.raise_for_status.side_effect = ValueError("invalid response")
    with unittest.mock.patch("markdown_this.fetchers.requests.get", return_value=response):
        assert fetch_youtube_video(VIDEO_URL) is None


def test_fetch_youtube_video_handles_empty_optional_content() -> None:
    response = unittest.mock.Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"title": "", "author_name": ""}
    with (
        _patch_oembed(response),
        unittest.mock.patch("markdown_this.fetchers.fetch_html", return_value=""),
        unittest.mock.patch("markdown_this.fetchers._fetch_youtube_transcript", return_value=None),
    ):
        assert fetch_youtube_video(VIDEO_URL) is None


def test_youtube_description_extracts_meta_tag_and_handles_request_errors() -> None:
    with unittest.mock.patch("markdown_this.fetchers.fetch_html", return_value=PAGE_HTML):
        assert fetchers_module._fetch_youtube_description(VIDEO_ID, timeout=3) == "A useful video description."

    with unittest.mock.patch(
        "markdown_this.fetchers.fetch_html",
        side_effect=requests.RequestException("network error"),
    ):
        assert fetchers_module._fetch_youtube_description(VIDEO_ID) == ""

    with unittest.mock.patch("markdown_this.fetchers.fetch_html", return_value='<meta name="other" content="x">'):
        assert fetchers_module._fetch_youtube_description(VIDEO_ID) == ""


def test_youtube_transcript_prefers_manual_transcript() -> None:
    transcript_list = unittest.mock.Mock()
    transcript_list.find_manually_created_transcript.return_value.fetch.return_value = [
        SimpleNamespace(text="Manual text")
    ]
    with unittest.mock.patch("markdown_this.fetchers.YouTubeTranscriptApi") as api:
        api.return_value.list.return_value = transcript_list
        assert fetchers_module._fetch_youtube_transcript(VIDEO_ID) == ("Manual text", False)


def test_youtube_transcript_falls_back_to_generated_transcript() -> None:
    transcript_list = unittest.mock.Mock()
    transcript_list.find_manually_created_transcript.side_effect = RuntimeError("not available")
    transcript_list.find_generated_transcript.return_value.fetch.return_value = [SimpleNamespace(text="Generated text")]
    with unittest.mock.patch("markdown_this.fetchers.YouTubeTranscriptApi") as api:
        api.return_value.list.return_value = transcript_list
        assert fetchers_module._fetch_youtube_transcript(VIDEO_ID) == ("Generated text", True)


def test_youtube_transcript_handles_missing_and_failed_transcripts() -> None:
    with unittest.mock.patch("markdown_this.fetchers.YouTubeTranscriptApi") as api:
        api.return_value.list.side_effect = CouldNotRetrieveTranscript(video_id=VIDEO_ID)
        assert fetchers_module._fetch_youtube_transcript(VIDEO_ID) is None

        api.return_value.list.side_effect = RuntimeError("network error")
        assert fetchers_module._fetch_youtube_transcript(VIDEO_ID) is None

    transcript_list = unittest.mock.Mock()
    transcript_list.find_manually_created_transcript.side_effect = RuntimeError("not available")
    transcript_list.find_generated_transcript.return_value.fetch.return_value = [SimpleNamespace(text=" ")]
    with unittest.mock.patch("markdown_this.fetchers.YouTubeTranscriptApi") as api:
        api.return_value.list.return_value = transcript_list
        assert fetchers_module._fetch_youtube_transcript(VIDEO_ID) is None


def test_extract_main_content_uses_youtube_special_handler() -> None:
    special_extractor = unittest.mock.Mock(return_value=("Video title", "**Description:** Video body"))
    with unittest.mock.patch.object(extractor_module, "SPECIAL_URL_EXTRACTORS", (special_extractor,)):
        title, markdown, fallback, intro = extractor_module.extract_main_content(VIDEO_URL)

    assert title == "Video title"
    assert "Video body" in markdown
    assert fallback == "Description: Video body"
    assert intro == "Description: Video body"
