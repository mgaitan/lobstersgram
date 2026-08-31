"""Request models accepted by the web service."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SourceMetadata(BaseModel):
    """Optional metadata supplied alongside raw HTML or Markdown."""

    title: str = ""
    author: str = ""
    url: str = ""
    date: str = ""
    image: str = ""
    type: str = ""

    def values(self) -> dict[str, str]:
        return {key: value for key, value in self.model_dump().items() if value}


class SourceRequest(BaseModel):
    """A URL, raw HTML, or already extracted Markdown document."""

    url: str | None = None
    html: str | None = None
    markdown: str | None = None
    metadata: SourceMetadata = Field(default_factory=SourceMetadata)
    access_token: str | None = None


class TelegraphResponse(BaseModel):
    """Response returned after a page is published."""

    url: str


class TelegraphJobResponse(BaseModel):
    """Public progress returned by optional Redis-backed publishing jobs."""

    id: str
    status: Literal[
        "queued",
        "publishing_articles",
        "publishing_brief",
        "adding_navigation",
        "completed",
        "failed",
    ]
    completed: int
    total: int
    status_url: str
    run_url: str
    url: str | None = None
    error: str | None = None
    source_url: str | None = None
