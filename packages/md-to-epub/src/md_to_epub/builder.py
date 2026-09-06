"""Create EPUB 3 files from already-normalized Markdown content."""

from __future__ import annotations

import hashlib
import io
import mimetypes
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from PIL import Image, UnidentifiedImageError
from sphinx.cmd.build import build_main

MAX_IMAGE_BYTES = 20 * 1024 * 1024
REMOTE_IMAGE_RE = re.compile(r"(?P<prefix>!\[[^\]]*\]\()(?P<url>https?://[^)\s]+)(?P<suffix>\))")
HTML_IMAGE_RE = re.compile(
    r"(?P<prefix><img\b[^>]*?\bsrc=[\"'])(?P<url>https?://[^\"']+)(?P<suffix>[\"'])", re.IGNORECASE
)


class EpubBuildError(RuntimeError):
    """Raised when Markdown cannot be turned into a valid EPUB."""


@dataclass(frozen=True)
class Chapter:
    """One navigable chapter in a book."""

    title: str
    markdown: str
    source_url: str = ""
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class Book:
    """Book metadata and its ordered chapters."""

    title: str
    chapters: tuple[Chapter, ...]
    author: str = ""
    language: str = "es"


def build_epub(book: Book) -> bytes:
    """Build an EPUB in an isolated temporary Sphinx project and return bytes."""
    _validate_book(book)
    with tempfile.TemporaryDirectory(prefix="md-to-epub-") as temporary:
        source_dir = Path(temporary) / "source"
        build_dir = Path(temporary) / "build"
        source_dir.mkdir()
        _write_project(book, source_dir)
        status = build_main(["-q", "-E", "-b", "epub", str(source_dir), str(build_dir)])
        if status:
            raise EpubBuildError(f"Sphinx EPUB build failed with status {status}")  # noqa: TRY003
        output = build_dir / "book.epub"
        try:
            return output.read_bytes()
        except FileNotFoundError as exc:
            raise EpubBuildError("Sphinx did not produce an EPUB file") from exc  # noqa: TRY003


def write_epub(book: Book, output: str | Path) -> Path:
    """Build an EPUB and write it to *output*."""
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(build_epub(book))
    return target


def _validate_book(book: Book) -> None:
    if not book.title.strip():
        raise EpubBuildError("Book title cannot be empty")  # noqa: TRY003
    if not book.chapters:
        raise EpubBuildError("Book must contain at least one chapter")  # noqa: TRY003
    if any(not chapter.title.strip() for chapter in book.chapters):
        raise EpubBuildError("Chapter titles cannot be empty")  # noqa: TRY003


def _write_project(book: Book, source_dir: Path) -> None:
    basename = "book"
    (source_dir / "conf.py").write_text(_configuration(book, basename), encoding="utf-8")
    chapter_names: list[str] = []
    for index, chapter in enumerate(book.chapters, start=1):
        name = f"chapter-{index:03d}"
        chapter_names.append(name)
        markdown = _chapter_markdown(chapter)
        markdown = _materialize_images(markdown, source_dir / "images")
        (source_dir / f"{name}.md").write_text(markdown, encoding="utf-8")
    toctree = "\n".join(chapter_names)
    index = f"# {book.title}\n\n```{{toctree}}\n:maxdepth: 2\n\n{toctree}\n```\n"
    (source_dir / "index.md").write_text(index, encoding="utf-8")


def _configuration(book: Book, basename: str) -> str:
    return "\n".join(
        (
            f"project = {book.title!r}",
            f"author = {book.author or 'Markdown Tools'!r}",
            f"language = {book.language!r}",
            'copyright = "2026, Markdown Tools"',
            'version = "1.0"',
            'extensions = ["myst_parser"]',
            'source_suffix = {".md": "markdown"}',
            'master_doc = "index"',
            f"epub_title = {book.title!r}",
            f"epub_author = {book.author or 'Markdown Tools'!r}",
            f"epub_publisher = {'Markdown Tools'!r}",
            'epub_copyright = "2026, Markdown Tools"',
            f"epub_language = {book.language!r}",
            f"epub_basename = {basename!r}",
            'epub_show_urls = "no"',
            "epub_tocdepth = 2",
            'suppress_warnings = ["epub.unknown_project_files"]',
            "",
        )
    )


def _chapter_markdown(chapter: Chapter) -> str:
    body = _without_front_matter(chapter.markdown.strip())
    if not re.match(r"^#(?:\s|$)", body):
        body = f"# {chapter.title}\n\n{body}" if body else f"# {chapter.title}"
    additions: list[str] = []
    if chapter.source_url and chapter.source_url not in body:
        additions.append(f"_Fuente original: [{chapter.source_url}]({chapter.source_url})_")
    if chapter.warnings:
        additions.append(
            "## Advertencias de extracción\n\n" + "\n".join(f"> {warning}" for warning in chapter.warnings)
        )
    return body + ("\n\n---\n\n" + "\n\n".join(additions) if additions else "") + "\n"


def _without_front_matter(markdown: str) -> str:
    if not markdown.startswith("---\n"):
        return markdown
    closing = markdown.find("\n---", 4)
    if closing == -1:
        return markdown
    return markdown[closing + len("\n---") :].lstrip()


def _materialize_images(markdown: str, image_dir: Path) -> str:
    image_urls = list(
        dict.fromkeys(
            [match.group("url") for match in REMOTE_IMAGE_RE.finditer(markdown)]
            + [match.group("url") for match in HTML_IMAGE_RE.finditer(markdown)]
        )
    )
    if not image_urls:
        return markdown
    image_dir.mkdir(parents=True, exist_ok=True)
    replacements: dict[str, str] = {}
    for url in image_urls:
        replacements[url] = _download_image(url, image_dir)
    for url, local_path in replacements.items():
        markdown = markdown.replace(url, local_path)
    return markdown


def _download_image(url: str, image_dir: Path) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise EpubBuildError(f"Unsupported image URL: {url}")  # noqa: TRY003
    try:
        request = Request(url, headers={"User-Agent": "md-to-epub"})
        with urlopen(request, timeout=20) as response:
            data = response.read(MAX_IMAGE_BYTES + 1)
            content_type = response.headers.get_content_type()
    except (HTTPError, URLError, OSError) as exc:
        raise EpubBuildError(f"Could not download image: {url}") from exc  # noqa: TRY003
    if len(data) > MAX_IMAGE_BYTES:
        raise EpubBuildError(  # noqa: TRY003
            f"Image is larger than {MAX_IMAGE_BYTES // (1024 * 1024)} MB: {url}"
        )
    suffix = _image_suffix(parsed.path, content_type)
    data, suffix = _convert_unsupported_image(data, suffix, url)
    filename = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16] + suffix
    (image_dir / filename).write_bytes(data)
    return f"images/{filename}"


def _convert_unsupported_image(data: bytes, suffix: str, url: str) -> tuple[bytes, str]:
    if suffix not in {".webp", ".bin"}:
        return data, suffix
    try:
        image = Image.open(io.BytesIO(data))
        converted = io.BytesIO()
        image.convert("RGB").save(converted, format="PNG")
    except (UnidentifiedImageError, OSError) as exc:
        raise EpubBuildError(f"Unsupported image format: {url}") from exc  # noqa: TRY003
    return converted.getvalue(), ".png"


def _image_suffix(path: str, content_type: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix in {".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"}:
        return suffix
    return mimetypes.guess_extension(content_type) or ".bin"
