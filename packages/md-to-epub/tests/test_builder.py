from __future__ import annotations

import zipfile
from io import BytesIO

import pytest
from md_to_epub import Book, Chapter, EpubBuildError, build_epub


def test_build_epub_creates_epub3_with_chapters() -> None:
    data = build_epub(
        Book(
            title="My book",
            author="Author",
            chapters=(
                Chapter("One", "# One\n\nFirst", source_url="https://example.com/one"),
                Chapter("Two", "---\ntitle: Two\n---\n\nSecond", warnings=("Page 2 was skipped",)),
            ),
        )
    )

    with zipfile.ZipFile(BytesIO(data)) as archive:
        assert archive.read("mimetype") == b"application/epub+zip"
        assert "chapter-001.xhtml" in archive.namelist()
        assert "chapter-002.xhtml" in archive.namelist()
        assert "nav.xhtml" in archive.namelist()
        assert "Fuente original" in archive.read("chapter-001.xhtml").decode()
        assert "Page 2 was skipped" in archive.read("chapter-002.xhtml").decode()


@pytest.mark.parametrize(
    "book",
    [Book(title="", chapters=(Chapter("One", "Text"),)), Book(title="Book", chapters=())],
)
def test_build_epub_rejects_invalid_books(book: Book) -> None:
    with pytest.raises(EpubBuildError):
        build_epub(book)


def test_build_epub_embeds_remote_images(monkeypatch: pytest.MonkeyPatch) -> None:
    class Headers:
        def get_content_type(self) -> str:
            return "image/png"

    class Response:
        headers = Headers()

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self, _limit: int) -> bytes:
            return bytes.fromhex(
                "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
                "0000000d49444154789c6360f8cfc000000301010018dd8db40000000049454e44ae426082"
            )

    monkeypatch.setattr("md_to_epub.builder.urlopen", lambda *_args, **_kwargs: Response())
    data = build_epub(Book(title="Pictures", chapters=(Chapter("One", "![Photo](https://example.com/photo)"),)))

    with zipfile.ZipFile(BytesIO(data)) as archive:
        assert any(name.startswith("_images/") for name in archive.namelist())
