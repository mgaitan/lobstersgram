"""Bookmarklet source generation."""

from __future__ import annotations

from urllib.parse import quote


def _script(url: str, action: str) -> str:
    endpoint = quote(url, safe=":/@?=&")
    target = "'_blank'" if action == "md" else "'_self'"
    fields = (
        "['html','title','source_url'].forEach((n,i)=>{"
        "const x=document.createElement('textarea');"
        "x.name=n;x.value=[document.documentElement.outerHTML,document.title,location.href][i];"
        "f.append(x)});"
    )
    result = (
        "const f=document.createElement('form');f.method='POST';f.action='"
        + endpoint
        + "';f.target="
        + target
        + ";"
        + fields
        + "document.body.append(f);f.submit()"
    )
    return "javascript:(()=>{" + result + "})()"


def build_bookmarklets(base_url: str) -> dict[str, str]:
    """Return permanent bookmarklet URLs for Markdown and Telegraph."""
    root = base_url.rstrip("/")
    return {"markdown": _script(root + "/md", "md"), "telegraph": _script(root + "/t/bookmarklet", "t")}
