# Overview

`md-to-epub` builds EPUB 3 books from already-normalized Markdown chapters.
It uses Sphinx and MyST for the document build, creates a navigable table of
contents, embeds remote images, and keeps source URLs and extraction warnings
inside the book.

The package deliberately does not fetch or extract articles. Callers use
`markdown-this` or another extractor first, then pass the resulting Markdown
to this package. `markdown-web` uses the same renderer for single documents and
briefs with article cards.
