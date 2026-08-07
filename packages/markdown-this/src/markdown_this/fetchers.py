"""HTTP fetchers and special URL handlers."""

from __future__ import annotations

import base64
import contextlib
import re
import urllib.parse
from logging import getLogger

import requests
from bs4 import BeautifulSoup, UnicodeDammit
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import CouldNotRetrieveTranscript

from markdown_this.markdown import (
    _extract_leading_heading,
    _make_markdown_images_absolute,
    _strip_badge_paragraphs,
)

DEFAULT_REQUEST_TIMEOUT = 20
GITHUB_REPO_PATH_PARTS = 2
logger = getLogger(__name__)

_GITHUB_REPO_RE = re.compile(r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/?#]+)(?:[/?#].*)?$")
_GITHUB_BLOB_RE = re.compile(
    r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/blob/(?P<branch>[^/]+)/(?P<path>.+\.(?:md|markdown))$",
    re.IGNORECASE,
)
_ARXIV_ABS_RE = re.compile(r"^https?://arxiv\.org/abs/(?P<arxiv_id>[^?#]+)(?:[?#].*)?$", re.IGNORECASE)
_YOUTUBE_RE = re.compile(
    r"^https?://(?:(?:www\.|m\.)?youtube\.com/(?:watch\?(?:.*&)?v=|embed/|shorts/)|youtu\.be/)"
    r"(?P<video_id>[A-Za-z0-9_-]{11})(?:[?&#].*)?$",
    re.IGNORECASE,
)


def fetch_url(url: str, timeout: int = DEFAULT_REQUEST_TIMEOUT) -> str:
    """Follow redirects and return the final URL."""
    logger.debug("fetch_url start url=%s", url)
    response = requests.get(
        url,
        timeout=timeout,
        allow_redirects=True,
        headers={"User-Agent": "lobsters-telegraph-bot"},
    )
    response.raise_for_status()
    logger.debug("fetch_url final url=%s status=%s", response.url, response.status_code)
    return response.url


def fetch_html(url: str, timeout: int = DEFAULT_REQUEST_TIMEOUT) -> str | None:
    """Fetch HTML and decode UTF-8, falling back to BeautifulSoup detection."""
    response = requests.get(url, timeout=timeout, headers={"User-Agent": "lobsters-telegraph-bot"})
    response.raise_for_status()
    try:
        return response.content.decode("utf-8")
    except UnicodeDecodeError:
        dammit = UnicodeDammit(response.content, is_html=True)
        return dammit.unicode_markup or response.content.decode("latin-1")


def _github_repo_match(url: str) -> re.Match[str] | None:
    """Return a match when *url* is a GitHub repository root URL."""
    match = _GITHUB_REPO_RE.match(url)
    if match is None:
        return None
    if len(urllib.parse.urlparse(url).path.strip("/").split("/")) != GITHUB_REPO_PATH_PARTS:
        return None
    return match


def _fetch_github_api_file(api_url: str, timeout: int = DEFAULT_REQUEST_TIMEOUT) -> str | None:
    """Fetch, decode, and normalize a Markdown file from the GitHub API."""
    try:
        response = requests.get(
            api_url,
            timeout=timeout,
            headers={"User-Agent": "lobsters-telegraph-bot", "Accept": "application/vnd.github+json"},
        )
        response.raise_for_status()
        data = response.json()
        name: str = data.get("name", "")
        if not name.lower().endswith((".md", ".markdown")):
            logger.debug("GitHub API file is not Markdown: name=%r url=%s", name, api_url)
            return None
        markdown = base64.b64decode(data.get("content", "")).decode("utf-8")
        markdown = _strip_badge_paragraphs(markdown)
        download_url: str = data.get("download_url") or ""
        if download_url:
            markdown = _make_markdown_images_absolute(markdown, download_url.rsplit("/", 1)[0] + "/")
    except (requests.RequestException, ValueError, KeyError) as exc:
        logger.warning("GitHub API file failed url=%s error=%s", api_url, exc)
        return None
    return markdown


def fetch_github_readme(url: str, timeout: int = DEFAULT_REQUEST_TIMEOUT) -> tuple[str, str] | None:
    """Return ``(title, markdown)`` for a GitHub repository root URL."""
    match = _github_repo_match(url)
    if match is None:
        return None
    owner, repo = match.group("owner"), match.group("repo")
    title = f"{owner}/{repo}"
    try:
        response = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}",
            timeout=timeout,
            headers={"User-Agent": "lobsters-telegraph-bot", "Accept": "application/vnd.github+json"},
        )
        response.raise_for_status()
        data = response.json()
        full_name = data.get("full_name") or title
        description = (data.get("description") or "").strip()
        title = f"{full_name} – {description}" if description else full_name  # noqa: RUF001
    except requests.RequestException as exc:
        logger.warning("GitHub repo info failed error=%s", exc)

    markdown = _fetch_github_api_file(f"https://api.github.com/repos/{owner}/{repo}/readme", timeout)
    if markdown is None:
        return None
    return title, markdown


def fetch_github_blob_markdown(url: str, timeout: int = DEFAULT_REQUEST_TIMEOUT) -> tuple[str, str] | None:
    """Return ``(title, markdown)`` for a GitHub Markdown blob URL."""
    match = _GITHUB_BLOB_RE.match(url)
    if match is None:
        return None
    owner, repo, branch, path = (match.group(name) for name in ("owner", "repo", "branch", "path"))
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={branch}"
    markdown = _fetch_github_api_file(api_url, timeout)
    if markdown is None:
        return None
    heading, markdown = _extract_leading_heading(markdown)
    return heading or f"{owner}/{repo}/{path}", markdown


def _parse_arxiv_html(html: str, arxiv_id: str) -> tuple[str, list[str]]:
    """Parse an arXiv abstract page into a title and Markdown fragments."""
    soup = BeautifulSoup(html, "html.parser")
    title_tag = soup.find("h1", class_="title")
    if title_tag:
        descriptor = title_tag.find("span", class_="descriptor")
        if descriptor:
            descriptor.extract()
        title = title_tag.get_text(separator=" ", strip=True)
    else:
        title = arxiv_id

    parts: list[str] = []
    authors_tag = soup.find("div", class_="authors")
    if authors_tag:
        descriptor = authors_tag.find("span", class_="descriptor")
        if descriptor:
            descriptor.extract()
        author_links = authors_tag.find_all("a")
        authors_text = ", ".join(author.get_text(strip=True) for author in author_links)
        if not authors_text:
            authors_text = authors_tag.get_text(separator=" ", strip=True)
        if authors_text:
            parts.append(f"**Authors:** {authors_text}")

    abstract_tag = soup.find("blockquote", class_="abstract")
    if abstract_tag:
        descriptor = abstract_tag.find("span", class_="descriptor")
        if descriptor:
            descriptor.extract()
        abstract_text = abstract_tag.get_text(separator=" ", strip=True)
        if abstract_text:
            parts.append(f"> {abstract_text}")
    return title, parts


def fetch_arxiv_abstract(url: str, timeout: int = DEFAULT_REQUEST_TIMEOUT) -> tuple[str, str] | None:
    """Return ``(title, markdown)`` for an arXiv abstract URL."""
    match = _ARXIV_ABS_RE.match(url)
    if match is None:
        return None
    arxiv_id = match.group("arxiv_id")
    abs_url = f"https://arxiv.org/abs/{arxiv_id}"
    try:
        html = fetch_html(abs_url, timeout)
    except requests.RequestException as exc:
        logger.warning("arXiv fetch failed url=%s error=%s", abs_url, exc)
        return None
    if not html:
        return None
    title, parts = _parse_arxiv_html(html, arxiv_id)
    if not parts:
        logger.warning("arXiv content extraction returned no content url=%s", abs_url)
        return None
    return title, "\n\n".join(parts)


def _fetch_youtube_oembed(video_id: str, timeout: int = DEFAULT_REQUEST_TIMEOUT) -> tuple[str, str] | None:
    """Fetch the title and channel name for a YouTube video."""
    oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
    try:
        response = requests.get(oembed_url, timeout=timeout, headers={"User-Agent": "lobsters-telegraph-bot"})
        response.raise_for_status()
        data = response.json()
        return data.get("title") or video_id, data.get("author_name", "")
    except (requests.RequestException, ValueError) as exc:
        logger.warning("YouTube oEmbed fetch failed video_id=%s error=%s", video_id, exc)
        return None


def _fetch_youtube_description(video_id: str, timeout: int = DEFAULT_REQUEST_TIMEOUT) -> str:
    """Fetch the description meta tag from a YouTube video page."""
    watch_url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        html = fetch_html(watch_url, timeout)
        if html:
            soup = BeautifulSoup(html, "html.parser")
            description = soup.find("meta", attrs={"name": "description"})
            if description:
                return (description.get("content") or "").strip()
    except requests.RequestException as exc:
        logger.warning("YouTube description fetch failed video_id=%s error=%s", video_id, exc)
    return ""


def _fetch_youtube_transcript(video_id: str) -> tuple[str, bool] | None:
    """Fetch an English transcript, preferring manual over auto-generated text."""
    try:
        transcript_list = YouTubeTranscriptApi().list(video_id)
    except CouldNotRetrieveTranscript as exc:
        logger.debug("YouTube transcript unavailable video_id=%s error=%s", video_id, exc)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("YouTube transcript fetch failed video_id=%s error=%s", video_id, exc)
        return None

    with contextlib.suppress(Exception):
        transcript = transcript_list.find_manually_created_transcript(["en"]).fetch()
        text = " ".join(snippet.text for snippet in transcript).strip()
        if text:
            return text, False

    with contextlib.suppress(Exception):
        transcript = transcript_list.find_generated_transcript(["en"]).fetch()
        text = " ".join(snippet.text for snippet in transcript).strip()
        if text:
            return text, True

    return None


def fetch_youtube_video(url: str, timeout: int = DEFAULT_REQUEST_TIMEOUT) -> tuple[str, str] | None:
    """Return ``(title, markdown)`` for a supported YouTube video URL."""
    match = _YOUTUBE_RE.match(url)
    if match is None:
        return None

    video_id = match.group("video_id")
    oembed = _fetch_youtube_oembed(video_id, timeout)
    if oembed is None:
        return None
    title, author = oembed

    parts: list[str] = []
    if author:
        parts.append(f"**Channel:** {author}")

    description = _fetch_youtube_description(video_id, timeout)
    if description:
        parts.append(f"**Description:** {description}")

    if transcript_result := _fetch_youtube_transcript(video_id):
        transcript_text, is_generated = transcript_result
        label = "Transcript (auto-generated)" if is_generated else "Transcript"
        parts.append(f"**{label}:**\n\n> {transcript_text}")

    if not parts:
        logger.warning("YouTube content extraction returned no content video_id=%s", video_id)
        return None
    return title, "\n\n".join(parts)
