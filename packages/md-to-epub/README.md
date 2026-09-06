# md-to-epub

Build EPUB 3 books from one or more Markdown chapters. The package uses Sphinx
and MyST for the document build, embeds remote Markdown images, and keeps
chapter sources and extraction warnings readable in the resulting book.

```python
from md_to_epub import Book, Chapter, build_epub

book = Book(
    title="A small book",
    author="An author",
    chapters=(Chapter(title="First chapter", markdown="# First chapter\n\nText"),),
)
epub_bytes = build_epub(book)
```

The package does not fetch or extract articles. Callers such as `markdown-web`
can use `markdown-this` first and pass the normalized Markdown here.
