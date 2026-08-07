"""FastAPI application for Markdown extraction and Telegraph publishing."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from markdown_web.bookmarklet import build_bookmarklets
from markdown_web.schemas import SourceMetadata, SourceRequest
from markdown_web.service import (
    SourceError,
    bookmarklet_tokens,
    prepare_content,
    publish_content,
    require_bookmarklet_token,
    telegraph_tokens,
)

app = FastAPI(title="Page to Telegraph", description="Extract Markdown and publish it to Telegraph")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["POST"], allow_headers=["*"])
PACKAGE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=PACKAGE_DIR / "static"), name="static")


def _path_source(url: str, request: Request) -> str:
    if request.url.query:
        return f"{url}?{request.url.query}"
    return url


async def _request_data(request: Request) -> SourceRequest:
    content_type = request.headers.get("content-type", "").split(";", 1)[0]
    body = await request.body()
    if content_type == "application/json":
        try:
            return SourceRequest.model_validate(json.loads(body or b"{}"))
        except (json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Invalid JSON request") from exc
    if content_type in {"text/html", "text/plain"}:
        metadata = SourceMetadata(
            title=request.headers.get("x-title", ""),
            author=request.headers.get("x-author-name", ""),
            url=request.headers.get("x-source-url", ""),
            date=request.headers.get("x-published-date", ""),
            image=request.headers.get("x-image-url", ""),
        )
        return SourceRequest(html=body.decode("utf-8"), metadata=metadata)
    if content_type == "application/x-www-form-urlencoded":
        values = {key: items[-1] for key, items in parse_qs(body.decode("utf-8")).items() if items}
        metadata = SourceMetadata(
            title=values.pop("title", ""),
            author=values.pop("author", ""),
            url=values.pop("source_url", ""),
            date=values.pop("date", ""),
            image=values.pop("image", ""),
        )
        return SourceRequest(**values, metadata=metadata)
    raise HTTPException(status_code=415, detail="Use application/json, text/html, or form-urlencoded")


def _source_request_from_path(url: str, request: Request) -> SourceRequest:
    return SourceRequest(url=_path_source(url, request))


def _handle_source_error(exc: Exception) -> HTTPException:
    if isinstance(exc, SourceError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=502, detail=str(exc))


def _authorization_token(request: Request) -> str:
    value = request.headers.get("authorization", "")
    scheme, _, token = value.partition(" ")
    return token if scheme.lower() == "bearer" else ""


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/md/{url:path}", response_class=PlainTextResponse)
def markdown_from_url(url: str, request: Request) -> PlainTextResponse:
    try:
        prepared = prepare_content(_source_request_from_path(url, request))
    except Exception as exc:
        raise _handle_source_error(exc) from exc
    return PlainTextResponse(prepared.markdown, media_type="text/markdown")


@app.post("/md", response_class=PlainTextResponse)
async def markdown_from_post(request: Request) -> PlainTextResponse:
    source = await _request_data(request)
    try:
        prepared = prepare_content(source)
    except Exception as exc:
        raise _handle_source_error(exc) from exc
    return PlainTextResponse(prepared.markdown, media_type="text/markdown")


@app.get("/t/{url:path}")
def telegraph_from_url(url: str, request: Request) -> RedirectResponse:
    try:
        source_url = _path_source(url, request)
        target = publish_content(SourceRequest(url=source_url), cache_key=source_url)
    except Exception as exc:
        raise _handle_source_error(exc) from exc
    return RedirectResponse(
        target,
        status_code=303,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.post("/t")
async def telegraph_from_post(request: Request) -> JSONResponse:
    source = await _request_data(request)
    key = request.headers.get("x-bookmarklet-key")
    if key:
        try:
            source = source.model_copy(update={"access_token": require_bookmarklet_token(key)})
        except SourceError as exc:
            raise _handle_source_error(exc) from exc
    elif not source.access_token:
        source = source.model_copy(update={"access_token": _authorization_token(request) or None})
    try:
        target = publish_content(source, key)
    except Exception as exc:
        raise _handle_source_error(exc) from exc
    return JSONResponse({"url": target})


@app.get("/bookmarklet/", response_class=HTMLResponse)
def bookmarklet_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="bookmarklet.html", context={"bookmarklets": None})


@app.post("/bookmarklet/", response_class=HTMLResponse)
async def create_bookmarklet(request: Request) -> HTMLResponse:
    body = await request.body()
    values = {key: items[-1] for key, items in parse_qs(body.decode("utf-8")).items() if items}
    try:
        token = telegraph_tokens.resolve(values.get("access_token") or None)
    except Exception as exc:
        raise _handle_source_error(exc) from exc
    key = bookmarklet_tokens.create(token)
    bookmarks = build_bookmarklets(str(request.base_url).rstrip("/"), key)
    return templates.TemplateResponse(request=request, name="bookmarklet.html", context={"bookmarklets": bookmarks})
