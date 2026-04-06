"""Content fetching, extraction, and normalization."""

from __future__ import annotations

import base64
import contextlib
import re
import urllib.parse
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup, UnicodeDammit
from bs4.element import Tag
from markdownify import markdownify as html_to_md
from readability import Document

from lobstergram import config

# Matches a GitHub repository root URL such as https://github.com/owner/repo
# (with optional trailing slash or query/fragment).  URLs with additional path
# segments (issues, pull-requests, blob/tree paths, etc.) will be excluded by
# the path-length check in _github_repo_match().
_GITHUB_REPO_RE = re.compile(
    r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/?#]+)(?:[/?#].*)?$"
)

# Matches a single badge expressed as a Markdown image-inside-link:
#   [![alt text](image_url)](link_url)
# Used to detect and remove badge-only paragraphs from README content.
_BADGE_RE = re.compile(r"\[!\[[^\]]*\]\([^)]+\)\]\([^)]+\)")


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
    # Try UTF-8 first: the vast majority of modern pages are UTF-8 even when
    # they don't advertise it in the Content-Type header.  If the raw bytes are
    # not valid UTF-8, fall back to UnicodeDammit (BeautifulSoup's encoding
    # detective), which checks <meta charset> / <meta http-equiv="Content-Type">
    # before statistical detection — far more reliable than requests' ISO-8859-1
    # default or pure statistical analysis alone.
    try:
        return r.content.decode("utf-8")
    except UnicodeDecodeError:
        dammit = UnicodeDammit(r.content, is_html=True)
        # latin-1 is a lossless last resort: every byte maps to a Unicode code point,
        # so it never raises UnicodeDecodeError.
        return dammit.unicode_markup or r.content.decode("latin-1")


def _github_repo_match(url: str) -> re.Match[str] | None:
    """Return a regex match for *url* if it is a GitHub repository root URL.

    Only the two-segment path ``/owner/repo`` (with optional trailing slash or
    query/fragment) is accepted.  URLs with deeper paths (issues, pull-requests,
    file trees, etc.) return *None*.
    """
    m = _GITHUB_REPO_RE.match(url)
    if m is None:
        return None
    # Reject URLs whose path has more than two non-empty segments (owner + repo).
    path_parts = urllib.parse.urlparse(url).path.strip("/").split("/")
    if len(path_parts) != 2:  # noqa: PLR2004
        return None
    return m


def _strip_badge_paragraphs(markdown: str) -> str:
    """Remove badge-only paragraphs from *markdown*.

    A paragraph is considered badge-only when it consists entirely of
    ``[![alt](img_url)](link_url)`` patterns and whitespace.  Such paragraphs
    (common at the top of GitHub READMEs) render as broken or empty blocks on
    Telegraph because many badge image hosts (e.g. shields.io) are not served
    as Telegraph-compatible images.  Removing them prevents empty vertical
    space in the rendered page and ensures ``extract_intro`` skips them in
    favour of the actual description text.
    """
    result: list[str] = []
    for para in markdown.split("\n\n"):
        remaining = _BADGE_RE.sub("", para).strip()
        if remaining:
            result.append(para)
    return "\n\n".join(result)


def _make_markdown_images_absolute(markdown: str, base_url: str) -> str:
    """Resolve relative image URLs in *markdown* against *base_url*.

    Absolute URLs (``http://``, ``https://``, ``data:``) are left unchanged.
    Relative paths such as ``./screenshot.png`` or ``docs/img.png`` are joined
    with *base_url* so that images render correctly when the Markdown is
    displayed outside the repository (e.g. on Telegraph).
    """

    def _replace(m: re.Match[str]) -> str:
        alt, img_url = m.group(1), m.group(2)
        if img_url.startswith(("http://", "https://", "data:")):
            return m.group(0)
        return f"![{alt}]({urllib.parse.urljoin(base_url, img_url)})"

    return re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", _replace, markdown)


def fetch_github_readme(url: str) -> tuple[str, str] | None:
    """Return ``(title, markdown)`` for a GitHub repository root URL.

    Uses the GitHub REST API to fetch the repository description (for the
    title) and the README source (for the Markdown content), bypassing
    HTML rendering artefacts such as stripped code blocks and missing
    headings that affect Readability-based extraction of GitHub pages.

    Relative image URLs in the README are resolved to absolute
    ``raw.githubusercontent.com`` URLs so that images render on Telegraph.

    Returns *None* when *url* is not a GitHub repository root URL or when
    any API request fails (the caller falls back to HTML extraction).
    """
    m = _github_repo_match(url)
    if m is None:
        return None

    owner, repo = m.group("owner"), m.group("repo")
    headers = {
        "User-Agent": "lobsters-telegraph-bot",
        "Accept": "application/vnd.github+json",
    }

    # Fetch repo metadata for the page title.
    title = f"{owner}/{repo}"
    try:
        r = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}",
            timeout=config.REQUEST_TIMEOUT,
            headers=headers,
        )
        r.raise_for_status()
        data = r.json()
        full_name = data.get("full_name") or title
        description = (data.get("description") or "").strip()
        title = f"{full_name} – {description}" if description else full_name
    except requests.RequestException as exc:
        config.log("warn", f"fetch_github_readme repo info failed err={type(exc).__name__}: {exc}")

    # Fetch the README via the API (handles any default branch automatically).
    try:
        r = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}/readme",
            timeout=config.REQUEST_TIMEOUT,
            headers=headers,
        )
        r.raise_for_status()
        data = r.json()
        # Only use Markdown READMEs; fall back to HTML extraction for RST, etc.
        readme_name: str = data.get("name", "")
        if not readme_name.lower().endswith((".md", ".markdown")):
            config.log(
                "debug",
                f"fetch_github_readme non-markdown readme name={readme_name} url={url}",
            )
            return None
        content_b64: str = data.get("content", "")
        markdown = base64.b64decode(content_b64).decode("utf-8")
        # Remove badge-only paragraphs before storing the content so that
        # Telegraph does not render empty/broken badge image blocks and
        # extract_intro can find the actual description text.
        markdown = _strip_badge_paragraphs(markdown)
        # Resolve relative image paths using the raw content base URL.
        download_url: str = data.get("download_url") or ""
        if download_url:
            # Base URL is the directory containing the README file.
            raw_base = download_url.rsplit("/", 1)[0] + "/"
            markdown = _make_markdown_images_absolute(markdown, raw_base)
        config.log("debug", f"fetch_github_readme ok owner={owner} repo={repo} markdown_len={len(markdown)}")
        return title, markdown
    except (requests.RequestException, ValueError, KeyError) as exc:
        config.log("warn", f"fetch_github_readme readme failed err={type(exc).__name__}: {exc}")
        return None


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
    text = re.sub(r"\[\]\([^)]+\)", "", text)
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
    # For GitHub repository root URLs, prefer the raw README markdown so that
    # code blocks, headings, and other structures are preserved faithfully.
    if github_result := fetch_github_readme(url):
        title, markdown = github_result
        fallback_text = markdown_to_text(markdown)
        intro = extract_intro(markdown, fallback_text)
        config.log(
            "debug",
            f"extract_main_content used github readme url={url} markdown_len={len(markdown)}",
        )
        return title, markdown, fallback_text, intro

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
