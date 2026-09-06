# Technical Reference

The public API contains:

- `Chapter`: title, Markdown, optional source URL, and extraction warnings.
- `Book`: title, ordered chapters, author, and language.
- `build_epub(book)`: returns EPUB bytes.
- `write_epub(book, output)`: writes the EPUB to a path.

Each build uses a temporary Sphinx project with a generated `conf.py`,
`index.md`, and one Markdown source per chapter. Only the MyST extension is
enabled. Remote HTTP(S) images are downloaded into the temporary project and
rewritten before Sphinx builds the EPUB.
