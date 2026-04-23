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

# Matches a GitHub blob URL for a Markdown file, e.g.:
#   https://github.com/owner/repo/blob/main/path/to/file.md
_GITHUB_BLOB_RE = re.compile(
    r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/blob/(?P<branch>[^/]+)/(?P<path>.+\.(?:md|markdown))$",
    re.IGNORECASE,
)

# Matches an arXiv abstract URL such as https://arxiv.org/abs/2604.07902
# or https://arxiv.org/abs/hep-th/9711200 (older-style IDs with a category prefix).
_ARXIV_ABS_RE = re.compile(
    r"^https?://arxiv\.org/abs/(?P<arxiv_id>[^?#]+)(?:[?#].*)?$",
    re.IGNORECASE,
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


def _make_markdown_links_absolute(markdown: str, base_url: str) -> str:
    """Resolve relative Markdown link URLs in *markdown* against *base_url*."""

    def _replace(m: re.Match[str]) -> str:
        text, href = m.group(1), m.group(2).strip()
        if href.startswith(("http://", "https://", "mailto:", "tel:", "data:")):
            return m.group(0)
        absolute = urllib.parse.urljoin(base_url, href)
        if not absolute.startswith(("http://", "https://")):
            return m.group(0)
        return f"[{text}]({absolute})"

    return re.sub(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)", _replace, markdown)


def _fetch_github_api_file(api_url: str) -> str | None:
    """Fetch a Markdown file from the GitHub REST API.

    *api_url* must point to a GitHub API endpoint that returns a single-file
    object — either ``/repos/{owner}/{repo}/readme`` or
    ``/repos/{owner}/{repo}/contents/{path}``.  Both endpoints share the same
    ``{name, content (base64), download_url}`` response shape.

    Returns the processed Markdown string (badge paragraphs stripped, relative
    image URLs resolved to absolute ``raw.githubusercontent.com`` paths), or
    *None* when the file is not a Markdown file or when the request fails.
    """
    try:
        r = requests.get(
            api_url,
            timeout=config.REQUEST_TIMEOUT,
            headers={
                "User-Agent": "lobsters-telegraph-bot",
                "Accept": "application/vnd.github+json",
            },
        )
        r.raise_for_status()
        data = r.json()
        name: str = data.get("name", "")
        if not name.lower().endswith((".md", ".markdown")):
            config.log("debug", f"_fetch_github_api_file non-markdown name={name!r} url={api_url}")
            return None
        content_b64: str = data.get("content", "")
        markdown = base64.b64decode(content_b64).decode("utf-8")
        markdown = _strip_badge_paragraphs(markdown)
        download_url: str = data.get("download_url") or ""
        if download_url:
            raw_base = download_url.rsplit("/", 1)[0] + "/"
            markdown = _make_markdown_images_absolute(markdown, raw_base)
    except (requests.RequestException, ValueError, KeyError) as exc:
        config.log("warn", f"_fetch_github_api_file failed url={api_url} err={type(exc).__name__}: {exc}")
        return None
    else:
        return markdown


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

    # Fetch repo metadata for the page title.
    title = f"{owner}/{repo}"
    try:
        r = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}",
            timeout=config.REQUEST_TIMEOUT,
            headers={"User-Agent": "lobsters-telegraph-bot", "Accept": "application/vnd.github+json"},
        )
        r.raise_for_status()
        data = r.json()
        full_name = data.get("full_name") or title
        description = (data.get("description") or "").strip()
        title = f"{full_name} – {description}" if description else full_name
    except requests.RequestException as exc:
        config.log("warn", f"fetch_github_readme repo info failed err={type(exc).__name__}: {exc}")

    # Fetch the README via the shared helper (handles any default branch automatically).
    markdown = _fetch_github_api_file(f"https://api.github.com/repos/{owner}/{repo}/readme")
    if markdown is None:
        return None
    config.log("debug", f"fetch_github_readme ok owner={owner} repo={repo} markdown_len={len(markdown)}")
    return title, markdown


def _extract_leading_heading(markdown: str) -> tuple[str | None, str]:
    """Extract and remove the first heading from *markdown*.

    Returns ``(heading_text, rest_of_markdown)`` when a heading is found at
    the very start of the content (after stripping blank lines).  Returns
    ``(None, original_markdown)`` when no leading heading is present.
    """
    stripped = markdown.lstrip("\n")
    m = re.match(r"^#{1,6}\s+(.*?)\s*$", stripped, re.MULTILINE)
    if m:
        return m.group(1).strip(), stripped[m.end() :].lstrip("\n")
    return None, markdown


def fetch_github_blob_markdown(url: str) -> tuple[str, str] | None:
    """Return ``(title, markdown)`` for a GitHub blob URL pointing to a Markdown file.

    Uses the GitHub Contents API (``/repos/{owner}/{repo}/contents/{path}?ref={branch}``)
    to fetch the file — the same mechanism used by ``fetch_github_readme`` for READMEs —
    so that badge stripping, image resolution, and error handling are shared via
    ``_fetch_github_api_file``.  The first heading in the file is extracted as the
    page title and stripped from the content body.

    Returns *None* when *url* does not match a GitHub Markdown blob URL or
    when the fetch fails (the caller falls back to HTML extraction).
    """
    m = _GITHUB_BLOB_RE.match(url)
    if m is None:
        return None

    owner, repo, branch, path = m.group("owner"), m.group("repo"), m.group("branch"), m.group("path")

    # Use the GitHub Contents API with an explicit ref so the correct branch or
    # commit is fetched.  The response format matches the readme endpoint, so
    # the shared _fetch_github_api_file helper handles fetching, decoding, and
    # post-processing identically to how fetch_github_readme works.
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={branch}"
    markdown = _fetch_github_api_file(api_url)
    if markdown is None:
        return None

    heading, markdown = _extract_leading_heading(markdown)
    title = heading or f"{owner}/{repo}/{path}"

    config.log("debug", f"fetch_github_blob_markdown ok url={url} title={title!r} markdown_len={len(markdown)}")
    return title, markdown


def _parse_arxiv_html(html: str, arxiv_id: str) -> tuple[str, list[str]]:
    """Parse arXiv abstract page HTML and return ``(title, content_parts)``.

    Extracts the paper title, authors, and abstract from the page.  The
    ``content_parts`` list contains Markdown-formatted strings suitable for
    joining into the final article body.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Title — <h1 class="title mathjax"> contains a nested <span class="descriptor">Title:</span>
    title_tag = soup.find("h1", class_="title")
    if title_tag:
        descriptor = title_tag.find("span", class_="descriptor")
        if descriptor:
            descriptor.extract()
        title = title_tag.get_text(separator=" ", strip=True)
    else:
        title = arxiv_id

    parts: list[str] = []

    # Authors — <div class="authors"> contains links for each author
    authors_tag = soup.find("div", class_="authors")
    if authors_tag:
        descriptor = authors_tag.find("span", class_="descriptor")
        if descriptor:
            descriptor.extract()
        # Collect individual author names from <a> links; fall back to the
        # whole tag text if no links are present.
        author_links = authors_tag.find_all("a")
        if author_links:
            authors_text = ", ".join(a.get_text(strip=True) for a in author_links)
        else:
            authors_text = authors_tag.get_text(separator=" ", strip=True)
        if authors_text:
            parts.append(f"**Authors:** {authors_text}")

    # Abstract — <blockquote class="abstract mathjax">
    abstract_tag = soup.find("blockquote", class_="abstract")
    if abstract_tag:
        descriptor = abstract_tag.find("span", class_="descriptor")
        if descriptor:
            descriptor.extract()
        abstract_text = abstract_tag.get_text(separator=" ", strip=True)
        if abstract_text:
            parts.append(f"> {abstract_text}")

    return title, parts


def fetch_arxiv_abstract(url: str) -> tuple[str, str] | None:
    """Return ``(title, markdown)`` for an arXiv abstract URL.

    Fetches the abstract page at ``https://arxiv.org/abs/{id}`` and extracts
    the paper title, authors, and abstract using BeautifulSoup.  The result is
    formatted as Markdown with the authors in bold and the abstract as a
    blockquote.

    Returns *None* when *url* does not match an arXiv abstract URL or when the
    fetch or parsing fails (the caller falls back to generic HTML extraction).
    """
    m = _ARXIV_ABS_RE.match(url)
    if m is None:
        return None

    arxiv_id = m.group("arxiv_id")
    abs_url = f"https://arxiv.org/abs/{arxiv_id}"

    try:
        html = fetch_html(abs_url)
    except requests.RequestException as exc:
        config.log("warn", f"fetch_arxiv_abstract fetch failed url={abs_url} err={type(exc).__name__}: {exc}")
        return None

    if not html:
        return None

    title, parts = _parse_arxiv_html(html, arxiv_id)

    if not parts:
        config.log("warn", f"fetch_arxiv_abstract no content extracted url={abs_url}")
        return None

    markdown = "\n\n".join(parts)
    config.log("debug", f"fetch_arxiv_abstract ok arxiv_id={arxiv_id!r} title={title!r} markdown_len={len(markdown)}")
    return title, markdown


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


_BROKEN_LINK_RE = re.compile(r"\[(\s*\n[ \t]*\n[ \t]*)([^\]]*)\]\(")


def _normalize_markdown_links(markdown: str) -> str:
    """Fix Markdown links broken by blank lines inside the opening bracket.

    When HTML is converted to Markdown, a ``<br>`` or block element between a
    literal ``[`` and the link text can introduce a blank line inside the link
    brackets, e.g.::

        [\n  \nWe need to evolve...](url)

    Mistletoe treats the blank line as a paragraph boundary and renders ``[``
    as a plain-text paragraph followed by ``We need to evolve...](url)`` as
    another paragraph, showing the raw URL instead of a hyperlink.

    This function collapses the leading whitespace/newlines so the link is
    recognised as valid Markdown.
    """

    def _fix(m: re.Match[str]) -> str:
        text = m.group(2).replace("\n", " ").strip()
        return f"[{text}]("

    return _BROKEN_LINK_RE.sub(_fix, markdown)


def strip_leading_title_heading(markdown: str, title: str) -> str:
    """Remove the leading heading from *markdown* if it duplicates *title*.

    Telegraph already shows the page title above the content.  If the
    extracted article content begins with a heading whose text matches the
    title, it would be rendered twice.  This function drops that first
    heading (and any blank lines immediately following it) so the title
    appears only once.

    The comparison is case-insensitive and ignores surrounding whitespace.
    """
    stripped = markdown.lstrip("\n")
    m = re.match(r"^#{1,6}\s+(.*)\s*$", stripped, re.MULTILINE)
    if m and m.group(1).strip().lower() == title.strip().lower():
        rest = stripped[m.end() :]
        return rest.lstrip("\n")
    return markdown


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
    # For GitHub blob URLs pointing to Markdown files, fetch the raw content
    # directly and use the first heading as the title.  This avoids the noisy
    # "file.md at main · owner/repo · GitHub" browser-tab title that Readability
    # would otherwise extract from the HTML page.
    if github_blob_result := fetch_github_blob_markdown(url):
        title, markdown = github_blob_result
        fallback_text = markdown_to_text(markdown)
        intro = extract_intro(markdown, fallback_text)
        config.log(
            "debug",
            f"extract_main_content used github blob url={url} markdown_len={len(markdown)}",
        )
        return title, markdown, fallback_text, intro

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

    # For arXiv abstract URLs, extract the paper title, authors, and abstract
    # directly from the abstract page HTML to avoid Readability returning an
    # empty or truncated result.
    if arxiv_result := fetch_arxiv_abstract(url):
        title, markdown = arxiv_result
        fallback_text = markdown_to_text(markdown)
        intro = extract_intro(markdown, fallback_text)
        config.log(
            "debug",
            f"extract_main_content used arxiv abstract url={url} markdown_len={len(markdown)}",
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
    extracted_markdown = _normalize_markdown_links(extracted_markdown)
    extracted_markdown = _make_markdown_links_absolute(extracted_markdown, url)
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
