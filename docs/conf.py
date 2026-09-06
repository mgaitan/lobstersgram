# Configuration file for the Sphinx documentation builder.

project = "Markdown Tools"
copyright = "2026, Martín Gaitán"  # noqa: A001 - Sphinx expects this name.
author = "Martín Gaitán"

extensions = [
    "myst_parser",
    "richterm.sphinxext",
    "sphinxcontrib.mermaid",
]

exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]
suppress_warnings = ["myst.xref_missing"]

html_theme = "sphinx_book_theme"

richterm_prompt = "[bold]$"
richterm_hide_command = False

myst_url_schemes = {
    "http": None,
    "https": None,
    "gh": {
        "url": "https://github.com/mgaitan/markdown-tools/blob/master/{path}#{fragment}",
        "title": "",
        "classes": ["github"],
    },
}

myst_fence_as_directive = ["mermaid"]
