"""Bookmarklet source generation."""

from __future__ import annotations

from urllib.parse import quote


def _script(url: str, action: str) -> str:
    endpoint = quote(url, safe=":/@?=&")
    headers = "{'Content-Type':'application/json'}"
    payload = (
        "JSON.stringify({html:document.documentElement.outerHTML,metadata:{url:location.href,title:document.title}})"
    )
    if action == "md":
        result = (
            "const w=window.open();fetch('"
            + endpoint
            + "',{method:'POST',headers:"
            + headers
            + ",body:"
            + payload
            + "}).then(r=>r.text()).then(t=>{const b=new Blob([t],"
            "{type:'text/markdown'});w.location=URL.createObjectURL(b)})"
            ".catch(e=>{w.document.body.innerText=e})"
        )
    else:
        result = (
            "fetch('"
            + endpoint
            + "',{method:'POST',headers:"
            + headers
            + ",body:"
            + payload
            + "}).then(r=>r.json()).then(d=>{if(d.url)location.href=d.url;"
            "else alert(d.detail||'Publish failed')}).catch(e=>alert(e))"
        )
    return "javascript:(()=>{" + result + "})()"


def build_bookmarklets(base_url: str) -> dict[str, str]:
    """Return permanent bookmarklet URLs for Markdown and Telegraph."""
    root = base_url.rstrip("/")
    return {"markdown": _script(root + "/md", "md"), "telegraph": _script(root + "/t", "t")}
