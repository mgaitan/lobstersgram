"""Tests for reusable media oEmbed extraction."""

from __future__ import annotations

import unittest.mock

import requests
from markdown_this import extract_main_content, fetch_media_oembed, split_front_matter
from markdown_this import fetchers as fetchers_module

VIMEO_URL = "https://vimeo.com/35941909"
DAILYMOTION_URL = "https://www.dailymotion.com/video/x84sh87"


class _OEmbedResponse:
    def __init__(self, data: object) -> None:
        self._data = data

    def raise_for_status(self) -> None:
        pass

    def json(self) -> object:
        return self._data


def test_fetch_media_oembed_extracts_vimeo_metadata_and_markdown() -> None:
    response = _OEmbedResponse(
        {
            "title": "A Vimeo video",
            "author_name": "Vimeo channel",
            "provider_name": "Vimeo",
            "description": "<p>A useful <strong>video</strong> description.</p>",
            "thumbnail_url": "https://i.vimeocdn.com/video.jpg",
            "type": "video",
            "html": '<iframe src="https://player.vimeo.com/video/35941909"></iframe>',
        }
    )
    with unittest.mock.patch("markdown_this.fetchers.requests.get", return_value=response) as get:
        result = fetch_media_oembed(VIMEO_URL, timeout=7)

    assert result is not None
    title, markdown = result
    metadata, body = split_front_matter(markdown)
    assert title == "A Vimeo video"
    assert metadata == {
        "author": "Vimeo channel",
        "image": "https://i.vimeocdn.com/video.jpg",
        "type": "video",
    }
    assert "**Provider:** Vimeo" in body
    assert "**Author:** Vimeo channel" in body
    assert "A useful **video** description." in body
    assert f"**Source:** {VIMEO_URL}" in body
    assert "**Embed:** https://player.vimeo.com/video/35941909" in body
    get.assert_called_once_with(
        "https://vimeo.com/api/oembed.json",
        params={"url": VIMEO_URL, "format": "json"},
        timeout=7,
        headers={"User-Agent": "lobsters-telegraph-bot"},
    )


def test_fetch_media_oembed_extracts_dailymotion_without_optional_fields() -> None:
    response = _OEmbedResponse({"title": "A Dailymotion video", "provider_name": "Dailymotion"})
    with unittest.mock.patch("markdown_this.fetchers.requests.get", return_value=response) as get:
        result = fetch_media_oembed(DAILYMOTION_URL)

    assert result is not None
    title, markdown = result
    metadata, body = split_front_matter(markdown)
    assert title == "A Dailymotion video"
    assert metadata == {"author": "Dailymotion"}
    assert "**Provider:** Dailymotion" in body
    assert f"**Source:** {DAILYMOTION_URL}" in body
    assert "**Embed:**" not in body
    assert get.call_args.kwargs["params"] == {"url": DAILYMOTION_URL, "format": "json"}


def test_fetch_media_oembed_rejects_non_media_and_unusable_oembed() -> None:
    assert fetch_media_oembed("https://example.com/video") is None

    with unittest.mock.patch(
        "markdown_this.fetchers.requests.get",
        side_effect=requests.RequestException("network error"),
    ):
        assert fetch_media_oembed(VIMEO_URL) is None

    bad_response = unittest.mock.Mock()
    bad_response.raise_for_status.return_value = None
    bad_response.json.side_effect = ValueError("bad json")
    with unittest.mock.patch("markdown_this.fetchers.requests.get", return_value=bad_response):
        assert fetch_media_oembed(VIMEO_URL) is None

    with unittest.mock.patch("markdown_this.fetchers.requests.get", return_value=_OEmbedResponse([])):
        assert fetch_media_oembed(VIMEO_URL) is None

    with unittest.mock.patch("markdown_this.fetchers.requests.get", return_value=_OEmbedResponse({"title": ""})):
        assert fetch_media_oembed(VIMEO_URL) is None


def test_media_oembed_helpers_cover_supported_hosts_and_empty_html() -> None:
    assert fetchers_module._media_oembed_endpoint("https://www.vimeo.com/35941909") == (
        "https://vimeo.com/api/oembed.json"
    )
    assert fetchers_module._media_oembed_endpoint("https://player.vimeo.com/video/35941909") == (
        "https://vimeo.com/api/oembed.json"
    )
    assert fetchers_module._media_oembed_endpoint("https://dai.ly/x84sh87") == (
        "https://www.dailymotion.com/services/oembed"
    )
    assert fetchers_module._extract_oembed_iframe_src("<div>No iframe</div>") == ""


def test_extract_main_content_uses_media_oembed_handler() -> None:
    response = _OEmbedResponse(
        {
            "title": "A Vimeo video",
            "author_name": "Vimeo channel",
            "provider_name": "Vimeo",
            "thumbnail_url": "https://i.vimeocdn.com/video.jpg",
            "type": "video",
        }
    )
    with unittest.mock.patch("markdown_this.fetchers.requests.get", return_value=response):
        title, markdown, fallback, intro = extract_main_content(VIMEO_URL)

    metadata, body = split_front_matter(markdown)
    assert title == "A Vimeo video"
    assert metadata == {
        "title": "A Vimeo video",
        "author": "Vimeo channel",
        "url": VIMEO_URL,
        "image": "https://i.vimeocdn.com/video.jpg",
        "type": "video",
    }
    assert "**Source:**" in body
    assert "A Vimeo video" not in fallback
    assert intro.startswith("Provider: Vimeo")
