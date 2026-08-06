"""Request models accepted by the web service."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SourceMetadata(BaseModel):
    """Optional metadata supplied alongside raw HTML or Markdown."""

    title: str = ""
    author: str = ""
    url: str = ""
    date: str = ""
    image: str = ""

    def values(self) -> dict[str, str]:
        return {key: value for key, value in self.model_dump().items() if value}


class SourceRequest(BaseModel):
    """A URL, raw HTML, or already extracted Markdown document."""

    url: str | None = None
    html: str | None = None
    markdown: str | None = None
    metadata: SourceMetadata = Field(default_factory=SourceMetadata)
    access_token: str | None = None
