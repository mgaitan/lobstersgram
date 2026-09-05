"""HTML cleanup helpers used before Markdown conversion."""

from __future__ import annotations

import contextlib
import urllib.parse

from bs4 import BeautifulSoup
from bs4.element import Tag

CHROME_TAGS = ("aside", "button", "form", "nav", "noscript", "script", "style", "template")


def _best_src_for_img(img: Tag) -> str:
    """Return the best candidate URL for an ``<img>`` element."""
    src = (img.get("src") or "").strip()
    if src and not src.startswith("data:"):
        return src

    data_src = (img.get("data-src") or "").strip()
    if data_src and not data_src.startswith("data:"):
        return data_src

    srcset = (img.get("srcset") or "").strip()
    if srcset:
        best_url, best_width = "", -1
        for candidate in srcset.split(","):
            parts = candidate.strip().split()
            if not parts:
                continue
            url = parts[0]
            width = 0
            if len(parts) > 1 and parts[1].endswith("w"):
                with contextlib.suppress(ValueError):
                    width = int(parts[1].removesuffix("w"))
            if width > best_width:
                best_width, best_url = width, url
        if best_url:
            return best_url
    return ""


def make_images_absolute(content_html: str, base_url: str) -> str:
    """Resolve image URLs and remove images that cannot be fetched over HTTP(S)."""
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


def strip_chrome(content_html: str) -> str:
    """Remove structural page chrome before Markdown conversion."""
    soup = BeautifulSoup(content_html, "html.parser")
    for tag in soup.find_all(CHROME_TAGS):
        tag.decompose()
    return str(soup)


def preprocess_figures(content_html: str) -> str:
    """Convert text figures to blockquotes while preserving image figures."""
    soup = BeautifulSoup(content_html, "html.parser")
    for figure in soup.find_all("figure"):
        figcaption = figure.find("figcaption")
        has_body_text = any(
            element.find_parent("figcaption") is None and bool(element.get_text(strip=True))
            for element in figure.find_all(["p", "div"])
        )
        if not has_body_text:
            continue

        if figcaption:
            figcaption.extract()
        blockquote = soup.new_tag("blockquote")
        for child in list(figure.children):
            blockquote.append(child.extract())
        figure.replace_with(blockquote)
        if figcaption:
            blockquote.insert_after(figcaption)
    return str(soup)
