"""Tests for content extraction and normalization helpers."""

# ruff: noqa: F401

from __future__ import annotations

import base64
import unittest.mock

import requests
from bs4 import BeautifulSoup
from url_to_markdown import (
    ContentDownloadError,
    _extract_leading_heading,
    _github_repo_match,
    _is_html_badge_block,
    _make_markdown_images_absolute,
    _make_markdown_links_absolute,
    _normalize_markdown_links,
    _strip_badge_paragraphs,
    extract_intro,
    fetch_arxiv_abstract,
    fetch_github_blob_markdown,
    fetch_github_readme,
    fetch_html,
    fetch_url,
    make_images_absolute,
    markdown_to_text,
    preprocess_figures,
    strip_leading_title_heading,
)
from url_to_markdown import extractor as extractor_module
from url_to_markdown import html as html_module
from url_to_markdown import markdown as markdown_module

BASE = "https://example.com/articles/my-post/"

# ---------------------------------------------------------------------------
# _github_repo_match tests
# ---------------------------------------------------------------------------


def test_github_repo_match_plain_url() -> None:
    """A plain https://github.com/owner/repo URL matches."""
    m = _github_repo_match("https://github.com/hauntsaninja/git_bayesect")
    assert m is not None
    assert m.group("owner") == "hauntsaninja"
    assert m.group("repo") == "git_bayesect"


def test_github_repo_match_trailing_slash() -> None:
    """Trailing slash is accepted."""
    m = _github_repo_match("https://github.com/owner/repo/")
    assert m is not None


def test_github_repo_match_http_scheme() -> None:
    """http:// scheme is also accepted."""
    m = _github_repo_match("http://github.com/owner/repo")
    assert m is not None


def test_github_repo_match_issues_url_rejected() -> None:
    """URLs with sub-paths (issues, PRs, etc.) do not match."""
    assert _github_repo_match("https://github.com/owner/repo/issues") is None


def test_github_repo_match_blob_url_rejected() -> None:
    """File blob URLs do not match."""
    assert _github_repo_match("https://github.com/owner/repo/blob/main/README.md") is None


def test_github_repo_match_non_github_rejected() -> None:
    """Non-GitHub URLs do not match."""
    assert _github_repo_match("https://example.com/owner/repo") is None


def test_github_repo_match_user_profile_rejected() -> None:
    """A GitHub user profile URL (single path segment) does not match."""
    assert _github_repo_match("https://github.com/owner") is None


# ---------------------------------------------------------------------------
# _make_markdown_images_absolute tests
# ---------------------------------------------------------------------------

_RAW_BASE = "https://raw.githubusercontent.com/owner/repo/main/"


def test_make_markdown_images_absolute_relative_path() -> None:
    """Relative image paths are resolved to absolute raw.githubusercontent.com URLs."""
    md = "![screenshot](./screenshot.png)"
    result = _make_markdown_images_absolute(md, _RAW_BASE)
    assert "https://raw.githubusercontent.com/owner/repo/main/screenshot.png" in result


def test_make_markdown_images_absolute_subdir_path() -> None:
    """Subdirectory-relative paths are resolved correctly."""
    md = "![img](docs/img.png)"
    result = _make_markdown_images_absolute(md, _RAW_BASE)
    assert "https://raw.githubusercontent.com/owner/repo/main/docs/img.png" in result


def test_make_markdown_images_absolute_http_unchanged() -> None:
    """Absolute http:// image URLs are left unchanged."""
    md = "![img](https://example.com/img.png)"
    result = _make_markdown_images_absolute(md, _RAW_BASE)
    assert result == md


def test_make_markdown_images_absolute_data_uri_unchanged() -> None:
    """Data URIs are left unchanged."""
    md = "![img](data:image/png;base64,abc)"
    result = _make_markdown_images_absolute(md, _RAW_BASE)
    assert result == md


def test_make_markdown_images_absolute_no_images_noop() -> None:
    """Markdown with no images is returned unchanged."""
    md = "# Hello\n\nSome text without images."
    result = _make_markdown_images_absolute(md, _RAW_BASE)
    assert result == md


# ---------------------------------------------------------------------------
# _make_markdown_links_absolute tests
# ---------------------------------------------------------------------------


def test_make_markdown_links_absolute_root_relative() -> None:
    """Root-relative markdown links are resolved against the page URL."""
    md = "[LWN](//lwn.net/Articles/1066581/)\n[Telegraph](/Articles/1066581/)"
    result = _make_markdown_links_absolute(md, "https://telegra.ph/Using-LLMs-04-22")
    assert "[LWN](https://lwn.net/Articles/1066581/)" in result
    assert "[Telegraph](https://telegra.ph/Articles/1066581/)" in result


def test_make_markdown_links_absolute_relative_path() -> None:
    """Relative markdown links are resolved against the page URL path."""
    md = "[next](chapter-2)"
    result = _make_markdown_links_absolute(md, "https://example.com/docs/chapter-1")
    assert result == "[next](https://example.com/docs/chapter-2)"


def test_make_markdown_links_absolute_keeps_absolute_and_images() -> None:
    """Absolute links and markdown image syntax are left unchanged."""
    md = "[site](https://example.com) ![img](/logo.png)"
    result = _make_markdown_links_absolute(md, "https://telegra.ph/Using-LLMs-04-22")
    assert "[site](https://example.com)" in result
    assert "![img](/logo.png)" in result


# ---------------------------------------------------------------------------
# fetch_github_readme tests
# ---------------------------------------------------------------------------


def _make_fake_requests_get(repo_data: dict, readme_data: dict | None = None) -> object:
    """Return a mock for ``requests.get`` that returns canned API responses."""

    class _FakeResp:
        def __init__(self, data: dict) -> None:
            self._data = data

        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return self._data

    def _side_effect(url: str, **_kwargs: object) -> _FakeResp:
        if "readme" in url:
            return _FakeResp(readme_data or {})
        return _FakeResp(repo_data)

    return unittest.mock.patch("url_to_markdown.fetchers.requests.get", side_effect=_side_effect)


def test_fetch_github_readme_returns_title_and_markdown() -> None:
    """fetch_github_readme returns (title, markdown) for a repo root URL."""
    readme_md = "# Installation\n\n```\npip install mylib\n```\n"
    repo_data = {
        "full_name": "owner/repo",
        "description": "A cool library",
    }
    readme_data = {
        "name": "README.md",
        "content": base64.b64encode(readme_md.encode()).decode() + "\n",
        "download_url": "https://raw.githubusercontent.com/owner/repo/main/README.md",
    }
    with _make_fake_requests_get(repo_data, readme_data):
        result = fetch_github_readme("https://github.com/owner/repo")

    assert result is not None
    title, markdown = result
    assert "owner/repo" in title
    assert "A cool library" in title
    assert "# Installation" in markdown
    assert "pip install mylib" in markdown


def test_fetch_github_readme_resolves_relative_images() -> None:
    """Relative image URLs in the README are resolved to absolute raw.githubusercontent.com URLs."""
    readme_md = "![screenshot](./docs/screenshot.png)\n"
    repo_data = {"full_name": "owner/repo", "description": ""}
    readme_data = {
        "name": "README.md",
        "content": base64.b64encode(readme_md.encode()).decode(),
        "download_url": "https://raw.githubusercontent.com/owner/repo/main/README.md",
    }
    with _make_fake_requests_get(repo_data, readme_data):
        result = fetch_github_readme("https://github.com/owner/repo")

    assert result is not None
    _, markdown = result
    assert "https://raw.githubusercontent.com/owner/repo/main/docs/screenshot.png" in markdown


def test_fetch_github_readme_non_markdown_readme_returns_none() -> None:
    """fetch_github_readme returns None when the README is not a Markdown file."""
    repo_data = {"full_name": "owner/repo", "description": ""}
    readme_data = {
        "name": "README.rst",
        "content": base64.b64encode(b"RST content").decode(),
        "download_url": "https://raw.githubusercontent.com/owner/repo/main/README.rst",
    }
    with _make_fake_requests_get(repo_data, readme_data):
        result = fetch_github_readme("https://github.com/owner/repo")

    assert result is None


def test_fetch_github_readme_non_github_url_returns_none() -> None:
    """fetch_github_readme returns None immediately for non-GitHub URLs."""
    result = fetch_github_readme("https://example.com/owner/repo")
    assert result is None


def test_fetch_github_readme_subpath_url_returns_none() -> None:
    """fetch_github_readme returns None for GitHub URLs with sub-paths."""
    result = fetch_github_readme("https://github.com/owner/repo/issues/1")
    assert result is None


def test_fetch_github_readme_api_failure_returns_none() -> None:
    """fetch_github_readme returns None when the README API request fails."""
    repo_data = {"full_name": "owner/repo", "description": ""}

    class _FakeResp:
        def __init__(self, data: dict) -> None:
            self._data = data

        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return self._data

    def _side_effect(url: str, **_kwargs: object) -> _FakeResp:
        if "readme" in url:
            raise requests.RequestException
        return _FakeResp(repo_data)

    with unittest.mock.patch("url_to_markdown.fetchers.requests.get", side_effect=_side_effect):
        result = fetch_github_readme("https://github.com/owner/repo")

    assert result is None


# ---------------------------------------------------------------------------
# fetch_github_readme badge-stripping tests
# ---------------------------------------------------------------------------


def test_fetch_github_readme_strips_badge_paragraphs() -> None:
    """fetch_github_readme strips badge-only paragraphs from the README."""
    readme_md = (
        "# mylib\n\n"
        "[![npm](https://img.shields.io/npm/v/mylib)](https://npmjs.com/mylib) "
        "[![ci](https://img.shields.io/github/actions/workflow/status/owner/mylib/ci.yml)](https://github.com/owner/mylib/actions)\n\n"
        "mylib is a great library.\n"
    )
    repo_data = {"full_name": "owner/mylib", "description": "A great library"}
    readme_data = {
        "name": "README.md",
        "content": base64.b64encode(readme_md.encode()).decode(),
        "download_url": "https://raw.githubusercontent.com/owner/mylib/main/README.md",
    }
    with _make_fake_requests_get(repo_data, readme_data):
        result = fetch_github_readme("https://github.com/owner/mylib")

    assert result is not None
    _, markdown = result
    assert "shields.io" not in markdown
    assert "# mylib" in markdown
    assert "mylib is a great library." in markdown


# ---------------------------------------------------------------------------
