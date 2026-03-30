"""Content fetching, extraction, and normalization."""

from __future__ import annotations

import contextlib
import re
import urllib.parse
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup
from bs4.element import Tag
from markdownify import markdownify as html_to_md
from readability import Document

from lobstergram import config


@dataclass(frozen=True)
class Item:
    id: str
    title: str
    link: str
    discussion_link: str
    source: str
    tags: list[str]


class ContentDownloadError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("Failed to download content")


def fetch_url(url: str) -> str:
    # Follow redirects to final URL.
    config.log("debug", f"fetch_url start url={url}")
    r = requests.get(
        url,
        timeout=config.REQUEST_TIMEOUT,
        allow_redirects=True,
        headers={"User-Agent": "lobsters-telegraph-bot"},
    )
    r.raise_for_status()
    config.log("debug", f"fetch_url final url={r.url} status={r.status_code}")
    return r.url


def fetch_html(url: str) -> str | None:
    r = requests.get(
        url,
        timeout=config.REQUEST_TIMEOUT,
        headers={"User-Agent": "lobsters-telegraph-bot"},
    )
    r.raise_for_status()
    # requests defaults to ISO-8859-1 for text/html when the server doesn't
    # declare a charset in the Content-Type header (HTTP/1.1 spec §3.7.1).
    # Most modern sites serve UTF-8 without advertising it, causing multi-byte
    # characters (e.g. em-dash U+2014) to appear as mojibake (â€").
    # Use charset_normalizer/chardet detection instead of that ISO-8859-1 fallback.
    r.encoding = r.apparent_encoding or "utf-8"
    return r.text


def is_lobsters_discussion(url: str) -> bool:
    if not url:
        return False
    parsed = urllib.parse.urlparse(url)
    return parsed.netloc.endswith("lobste.rs") and parsed.path.startswith("/s/")


def normalize_id(entry: object) -> str:
    # Prefer feed-provided id/guid; fallback to link.
    for key in ("id", "guid", "link"):
        v = getattr(entry, key, None)
        if v:
            return str(v)
    return str(hash(getattr(entry, "title", "")))


def _best_src_for_img(img: Tag) -> str:
    """Return the best candidate URL for an ``<img>`` element.

    Checks attributes in priority order:
    1. ``src`` — used as-is when it is a non-empty, non-data-URI value.
    2. ``data-src`` — common lazy-loading pattern.
    3. ``srcset`` — picks the candidate with the highest ``w`` descriptor
       (or the last candidate when no width descriptors are present).
    """
    src = (img.get("src") or "").strip()
    if src and not src.startswith("data:"):
        return src

    data_src = (img.get("data-src") or "").strip()
    if data_src and not data_src.startswith("data:"):
        return data_src

    srcset = (img.get("srcset") or "").strip()
    if srcset:
        best_url, best_w = "", -1
        for entry in srcset.split(","):
            parts = entry.strip().split()
            if not parts:
                continue
            url = parts[0]
            w = 0
            if len(parts) > 1 and parts[1].endswith("w"):
                with contextlib.suppress(ValueError):
                    w = int(parts[1].removesuffix("w"))
            if w > best_w:
                best_w, best_url = w, url
        if best_url:
            return best_url

    return ""


def make_images_absolute(content_html: str, base_url: str) -> str:
    """Resolve relative image src attributes to absolute URLs.

    Images whose src cannot be made into an absolute ``http``/``https`` URL
    are removed entirely so that Telegraph never shows a broken image.

    Falls back to ``data-src`` (lazy-loading) and ``srcset`` when ``src`` is
    absent or a data-URI placeholder so that images from sites like Substack
    are preserved.
    """
    soup = BeautifulSoup(content_html, "html.parser")
    for img in soup.find_all("img"):
        src = _best_src_for_img(img)
        if not src:
            img.decompose()
            continue
        absolute = urllib.parse.urljoin(base_url, src)
        if absolute.startswith(("http://", "https://")):
            img["src"] = absolute
        else:
            img.decompose()
    return str(soup)


def preprocess_figures(content_html: str) -> str:
    """Convert <figure> elements containing quoted text to <blockquote> nodes.

    HTML ``<figure>`` elements have no Markdown equivalent, so they are
    normally flattened into plain paragraphs by markdownify, losing any
    visual quote structure.  This function detects figures whose *body*
    (i.e. the parts outside any ``<figcaption>``) contains text paragraphs
    or divs—typical of pull-quote or GitHub-embed figures—and replaces them
    with a ``<blockquote>`` so that the Markdown conversion preserves the
    quotation structure.  The optional ``<figcaption>`` is moved to
    immediately after the new blockquote so that attribution text is kept.

    Figures whose body contains only an image (no ``<p>`` or ``<div>``) are
    left unchanged so that ordinary image captions are not affected.
    """
    soup = BeautifulSoup(content_html, "html.parser")
    for figure in soup.find_all("figure"):
        figcaption = figure.find("figcaption")

        # Only convert figures whose body (outside figcaption) has *text* content.
        # A <div> or <p> that only wraps an image is not considered a text body so
        # that ordinary image figures (e.g. Substack's <figure><div><img/></div></figure>)
        # are left unchanged and their images are preserved.
        has_body_text = any(
            el.find_parent("figcaption") is None and bool(el.get_text(strip=True))
            for el in figure.find_all(["p", "div"])
        )
        if not has_body_text:
            continue

        # Detach figcaption before rebuilding the tree
        if figcaption:
            figcaption.extract()

        # Replace <figure> with <blockquote>, moving all remaining children
        blockquote = soup.new_tag("blockquote")
        for child in list(figure.children):
            blockquote.append(child.extract())
        figure.replace_with(blockquote)

        # Re-insert figcaption immediately after the new blockquote
        if figcaption:
            blockquote.insert_after(figcaption)

    return str(soup)


def markdown_to_text(markdown_text: str) -> str:
    text = markdown_text
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", "", text)
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^>\s?", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    return re.sub(r"[_*]{1,3}([^_*]+)[_*]{1,3}", r"\1", text)


def extract_intro(markdown_text: str, fallback_text: str) -> str:
    text = markdown_to_text(markdown_text)
    for chunk in text.split("\n\n"):
        line = chunk.strip()
        if not line:
            continue
        intro = line.replace("\n", " ").strip()
        if len(intro) >= config.INTRO_MIN_LENGTH:
            return intro
    # Fallback: first non-empty line from text
    for line in fallback_text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def extract_main_content(url: str) -> tuple[str, str, str, str]:
    """
    Returns (title, markdown_content, fallback_text, intro).
    """
    downloaded = fetch_html(url)
    if not downloaded:
        raise ContentDownloadError

    config.log("debug", f"extract_main_content downloaded_len={len(downloaded)} url={url}")
    content_html = ""
    title = url
    try:
        doc = Document(downloaded)
        content_html = doc.summary() or ""
        title = doc.title() or url
        config.log(
            "debug",
            f"extract_main_content readability_len={len(content_html)} url={url}",
        )
    except Exception as exc:  # noqa: BLE001
        config.log("warn", f"readability failed err={type(exc).__name__}: {exc}")

    if not content_html or len(content_html.strip()) < config.MIN_CONTENT_LENGTH:
        config.log("warn", f"extract_main_content content_len={len(content_html)} url={url}")
        content_html = downloaded

    content_html = make_images_absolute(content_html, url)
    content_html = preprocess_figures(content_html)

    extracted_markdown = html_to_md(content_html)
    config.log(
        "debug",
        f"extract_main_content markdown_len={len(extracted_markdown)} url={url}",
    )

    soup = BeautifulSoup(content_html, "html.parser")
    fallback_text = soup.get_text(separator="\n").strip()
    intro = extract_intro(extracted_markdown, fallback_text)
    return title, extracted_markdown, fallback_text, intro


def collect_new_items(entries: list[object], seen: set[str]) -> list[Item]:
    new_items: list[Item] = []
    for entry in entries:
        iid = normalize_id(entry)
        if iid in seen:
            continue

        link = getattr(entry, "link", "") or ""
        discussion_link = getattr(entry, "comments", "") or ""
        if not discussion_link and is_lobsters_discussion(link):
            discussion_link = link
        if is_lobsters_discussion(link):
            links = getattr(entry, "links", []) or []
            for link_info in links:
                href = link_info.get("href") or ""
                if href and not is_lobsters_discussion(href):
                    link = href
                    break
        title = getattr(entry, "title", link) or link
        source = urllib.parse.urlparse(link).netloc or "lobste.rs"
        tags = [t.get("term", "") for t in getattr(entry, "tags", []) or []]
        tags = [t for t in tags if t]
        new_items.append(
            Item(
                id=iid,
                title=title,
                link=link,
                discussion_link=discussion_link,
                source=source,
                tags=tags,
            )
        )
    return new_items
