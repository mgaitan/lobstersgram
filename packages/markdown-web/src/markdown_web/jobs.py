"""Durable, client-driven Telegraph publishing jobs stored in Redis."""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import time
from contextlib import suppress
from functools import lru_cache
from typing import Literal, Protocol

import redis
from pydantic import BaseModel, Field

from markdown_web.schemas import SourceMetadata, SourceRequest
from markdown_web.service import (
    PreparedContent,
    PublishedBriefArticle,
    add_brief_navigation,
    card_source_urls,
    prepare_content,
    publish_brief_article,
    publish_brief_page,
    telegraph_tokens,
)
from markdown_web.telegram import send_telegram_notifications

JOB_KEY_PREFIX = "markdown-web:telegraph-job"
JOB_TTL_SECONDS = 48 * 60 * 60
JOB_LOCK_SECONDS = 90
JOB_ID_RE = re.compile(r"[0-9a-f]{32}")
RELEASE_LOCK_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""

JobStatus = Literal[
    "queued",
    "publishing_articles",
    "publishing_brief",
    "adding_navigation",
    "completed",
    "failed",
]


class JobError(RuntimeError):
    """Base error for optional Redis-backed publishing jobs."""


class JobsUnavailableError(JobError):
    """Raised when Redis-backed jobs are not configured."""

    def __init__(self) -> None:
        super().__init__("Publishing jobs require REDIS_URL")


class JobInputError(JobError):
    """Raised when a request cannot be handled as a durable job."""


class JobNotFoundError(JobError):
    """Raised when a job does not exist or has expired."""

    def __init__(self, job_id: str) -> None:
        super().__init__(f"Publishing job not found: {job_id}")


class JobBusyError(JobError):
    """Raised when another request is already advancing the job."""

    def __init__(self, job_id: str) -> None:
        super().__init__(f"Publishing job is already running: {job_id}")


class RedisClient(Protocol):
    """Small redis-py surface used by the job store."""

    def set(self, name: str, value: str, *, ex: int, nx: bool = False) -> object:
        """Set a value with expiry and optional create-only behavior."""

    def get(self, name: str) -> str | bytes | None:
        """Return a stored value."""

    def eval(self, script: str, numkeys: int, *keys_and_args: str) -> object:
        """Evaluate the lock release script."""


class StoredArticle(BaseModel):
    """Serializable article content and its published Telegraph URL."""

    source_url: str
    title: str
    markdown: str
    fallback_text: str
    metadata: SourceMetadata
    intro: str = ""
    telegraph_url: str
    telegraph_urls: list[str] = Field(default_factory=list)
    page_markdowns: list[str] = Field(default_factory=list)

    @classmethod
    def from_published(cls, article: PublishedBriefArticle) -> StoredArticle:
        """Create stored state from a published article."""
        return cls(
            source_url=article.source_url,
            title=article.content.title,
            markdown=article.content.markdown,
            fallback_text=article.content.fallback_text,
            metadata=article.content.metadata,
            intro=article.content.intro,
            telegraph_url=article.telegraph_url,
            telegraph_urls=list(article.telegraph_urls),
            page_markdowns=list(article.page_markdowns),
        )

    def published(self) -> PublishedBriefArticle:
        """Restore the service-layer article value."""
        return PublishedBriefArticle(
            source_url=self.source_url,
            content=PreparedContent(
                title=self.title,
                markdown=self.markdown,
                fallback_text=self.fallback_text,
                metadata=self.metadata,
                intro=self.intro,
            ),
            telegraph_url=self.telegraph_url,
            telegraph_urls=tuple(self.telegraph_urls),
            page_markdowns=tuple(self.page_markdowns),
        )


class JobState(BaseModel):
    """Complete durable state for an incrementally published brief."""

    id: str
    status: JobStatus = "queued"
    request: SourceRequest
    source_urls: list[str] = Field(default_factory=list)
    articles: list[StoredArticle] = Field(default_factory=list)
    brief_url: str = ""
    next_navigation: int = 0
    error: str = ""
    failed_source: str = ""
    notify_telegram: str = ""
    telegram_notified: bool = False
    created_at: int
    updated_at: int

    @property
    def total_steps(self) -> int:
        """Return article, brief, and navigation stage count."""
        return len(self.source_urls) * 2 + 1

    @property
    def completed_steps(self) -> int:
        """Return how many externally visible stages have completed."""
        return len(self.articles) + bool(self.brief_url) + self.next_navigation


@lru_cache(maxsize=4)
def _redis_client_for_url(url: str) -> RedisClient:
    return redis.Redis.from_url(url, decode_responses=True)


def _redis_client() -> RedisClient:
    if not (url := os.getenv("REDIS_URL")):
        raise JobsUnavailableError
    return _redis_client_for_url(url)


def _job_key(job_id: str) -> str:
    return f"{JOB_KEY_PREFIX}:{job_id}"


def _lock_key(job_id: str) -> str:
    return f"{_job_key(job_id)}:lock"


def _validate_job_id(job_id: str) -> None:
    if not JOB_ID_RE.fullmatch(job_id):
        raise JobNotFoundError(job_id)


def _save_job(client: RedisClient, state: JobState, *, only_if_missing: bool = False) -> bool:
    saved = client.set(
        _job_key(state.id),
        state.model_dump_json(),
        ex=JOB_TTL_SECONDS,
        nx=only_if_missing,
    )
    return bool(saved)


def _load_job(client: RedisClient, job_id: str) -> JobState:
    _validate_job_id(job_id)
    if not (raw := client.get(_job_key(job_id))):
        raise JobNotFoundError(job_id)
    return JobState.model_validate_json(raw)


def _job_id(request: SourceRequest) -> str:
    payload = request.model_dump_json(exclude={"access_token"}, exclude_none=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


def create_job(request: SourceRequest) -> JobState:
    """Create or return an idempotent publishing job for Markdown input."""
    if request.markdown is None:
        msg = "Publishing jobs currently require a Markdown request"
        raise JobInputError(msg)
    if request.access_token:
        msg = "Publishing jobs use the service Telegraph account; do not send an access token"
        raise JobInputError(msg)

    clean_request = request.model_copy(update={"access_token": None})
    brief = prepare_content(clean_request)
    now = int(time.time())
    state = JobState(
        id=_job_id(clean_request),
        request=clean_request,
        source_urls=card_source_urls(brief.markdown),
        notify_telegram=brief.metadata.notify_telegram,
        created_at=now,
        updated_at=now,
    )
    client = _redis_client()
    if _save_job(client, state, only_if_missing=True):
        return state
    return _load_job(client, state.id)


def get_job(job_id: str) -> JobState:
    """Load a publishing job from Redis."""
    return _load_job(_redis_client(), job_id)


def _published_articles(state: JobState) -> list[PublishedBriefArticle]:
    return [article.published() for article in state.articles]


def _advance_job(state: JobState) -> None:
    token = telegraph_tokens.resolve()
    if len(state.articles) < len(state.source_urls):
        state.status = "publishing_articles"
        source_url = state.source_urls[len(state.articles)]
        state.failed_source = source_url
        article = publish_brief_article(source_url, token, warm_cache=False)
        state.articles.append(StoredArticle.from_published(article))
        state.failed_source = ""
        return

    articles = _published_articles(state)
    if not state.brief_url:
        state.status = "publishing_brief"
        brief = prepare_content(state.request)
        state.brief_url = publish_brief_page(brief, articles, token)
        if not articles:
            state.status = "completed"
        return

    if state.next_navigation < len(articles):
        state.status = "adding_navigation"
        index = state.next_navigation
        state.failed_source = articles[index].source_url
        add_brief_navigation(
            articles[index],
            index,
            articles,
            state.brief_url,
            token,
            warm_cache=False,
        )
        state.next_navigation += 1
        state.failed_source = ""
        if state.next_navigation == len(articles):
            state.status = "completed"
        return

    state.status = "completed"


def run_job(job_id: str) -> JobState:
    """Advance one bounded job stage and persist its result."""
    client = _redis_client()
    state = _load_job(client, job_id)
    if state.status == "completed":
        return state

    lock_token = secrets.token_urlsafe(24)
    if not client.set(_lock_key(job_id), lock_token, ex=JOB_LOCK_SECONDS, nx=True):
        raise JobBusyError(job_id)

    try:
        state = _load_job(client, job_id)
        if state.status == "completed":
            return state
        state.error = ""
        try:
            _advance_job(state)
            if state.status == "completed" and not state.telegram_notified:
                send_telegram_notifications(state.brief_url, state.notify_telegram)
                state.telegram_notified = True
        except Exception as exc:  # noqa: BLE001
            state.status = "failed"
            state.error = str(exc) or type(exc).__name__
        state.updated_at = int(time.time())
        _save_job(client, state)
        return state
    finally:
        with suppress(Exception):
            client.eval(RELEASE_LOCK_SCRIPT, 1, _lock_key(job_id), lock_token)
