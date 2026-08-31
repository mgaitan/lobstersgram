import pytest
from markdown_web import jobs
from markdown_web.schemas import SourceMetadata, SourceRequest
from markdown_web.service import PreparedContent, PublishedBriefArticle

ARTICLE_COUNT = 2
EXPECTED_TOTAL_STEPS = ARTICLE_COUNT * 2 + 1


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def set(self, name: str, value: str, *, ex: int, nx: bool = False) -> bool | None:
        if nx and name in self.values:
            return None
        self.values[name] = value
        return True

    def get(self, name: str) -> str | None:
        return self.values.get(name)

    def eval(self, _script: str, _numkeys: int, name: str, token: str) -> int:
        if self.values.get(name) != token:
            return 0
        del self.values[name]
        return 1


def _use_fake_redis(monkeypatch: pytest.MonkeyPatch) -> FakeRedis:
    fake = FakeRedis()
    monkeypatch.setattr(jobs, "_redis_client", lambda: fake)
    return fake


def _brief_request() -> SourceRequest:
    return SourceRequest(markdown=("# Brief\n\n![card](https://example.com/one)\n\n![card](https://example.com/two)"))


def _published_article(source_url: str, index: int) -> PublishedBriefArticle:
    content = PreparedContent(
        title=f"Article {index}",
        markdown=f"# Article {index}\n\nBody {index}",
        fallback_text=f"Body {index}",
        metadata=SourceMetadata(url=source_url),
        intro=f"Intro {index}",
    )
    return PublishedBriefArticle(source_url, content, f"https://telegra.ph/article-{index}")


def test_create_job_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _use_fake_redis(monkeypatch)

    first = jobs.create_job(_brief_request())
    second = jobs.create_job(_brief_request())

    assert first.id == second.id
    assert first.status == "queued"
    assert first.source_urls == ["https://example.com/one", "https://example.com/two"]
    assert first.total_steps == EXPECTED_TOTAL_STEPS
    assert list(fake.values) == [f"{jobs.JOB_KEY_PREFIX}:{first.id}"]


def test_run_job_advances_one_stage_at_a_time(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_fake_redis(monkeypatch)
    monkeypatch.setattr(jobs.telegraph_tokens, "resolve", lambda: "token")
    article_calls: list[tuple[str, bool]] = []
    navigation_calls: list[tuple[int, bool]] = []

    def fake_publish_article(source_url: str, _token: str, *, warm_cache: bool) -> PublishedBriefArticle:
        article_calls.append((source_url, warm_cache))
        return _published_article(source_url, len(article_calls))

    def fake_publish_brief(
        _brief: PreparedContent,
        articles: list[PublishedBriefArticle],
        _token: str,
    ) -> str:
        assert len(articles) == ARTICLE_COUNT
        return "https://telegra.ph/brief"

    def fake_add_navigation(
        _article: PublishedBriefArticle,
        index: int,
        _articles: list[PublishedBriefArticle],
        _brief_url: str,
        _token: str,
        *,
        warm_cache: bool,
    ) -> str:
        navigation_calls.append((index, warm_cache))
        return f"https://telegra.ph/article-{index + 1}"

    monkeypatch.setattr(jobs, "publish_brief_article", fake_publish_article)
    monkeypatch.setattr(jobs, "publish_brief_page", fake_publish_brief)
    monkeypatch.setattr(jobs, "add_brief_navigation", fake_add_navigation)

    state = jobs.create_job(_brief_request())
    progress = [jobs.run_job(state.id) for _ in range(state.total_steps)]

    assert [item.completed_steps for item in progress] == [1, 2, 3, 4, 5]
    assert [item.status for item in progress] == [
        "publishing_articles",
        "publishing_articles",
        "publishing_brief",
        "adding_navigation",
        "completed",
    ]
    assert progress[-1].brief_url == "https://telegra.ph/brief"
    assert article_calls == [
        ("https://example.com/one", False),
        ("https://example.com/two", False),
    ]
    assert navigation_calls == [(0, False), (1, False)]
    assert jobs.get_job(state.id).status == "completed"


def test_run_job_completes_markdown_without_cards(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_fake_redis(monkeypatch)
    monkeypatch.setattr(jobs.telegraph_tokens, "resolve", lambda: "token")
    monkeypatch.setattr(jobs, "publish_brief_page", lambda _brief, _articles, _token: "https://telegra.ph/page")

    state = jobs.create_job(SourceRequest(markdown="# Page\n\nBody"))
    result = jobs.run_job(state.id)

    assert result.status == "completed"
    assert result.completed_steps == result.total_steps == 1
    assert result.brief_url == "https://telegra.ph/page"


def test_run_job_persists_source_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_fake_redis(monkeypatch)
    monkeypatch.setattr(jobs.telegraph_tokens, "resolve", lambda: "token")

    def fail_article(_source_url: str, _token: str, *, warm_cache: bool) -> PublishedBriefArticle:
        assert warm_cache is False
        msg = "source refused extraction"
        raise ValueError(msg)

    monkeypatch.setattr(jobs, "publish_brief_article", fail_article)
    state = jobs.create_job(_brief_request())

    failed = jobs.run_job(state.id)

    assert failed.status == "failed"
    assert failed.error == "source refused extraction"
    assert failed.failed_source == "https://example.com/one"

    monkeypatch.setattr(jobs, "publish_brief_article", lambda source, _token, **_kwargs: _published_article(source, 1))
    retried = jobs.run_job(state.id)

    assert retried.status == "publishing_articles"
    assert retried.error == ""
    assert retried.failed_source == ""
    assert retried.completed_steps == 1


def test_run_job_rejects_concurrent_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _use_fake_redis(monkeypatch)
    state = jobs.create_job(_brief_request())
    fake.values[f"{jobs.JOB_KEY_PREFIX}:{state.id}:lock"] = "another-runner"

    with pytest.raises(jobs.JobBusyError, match="already running"):
        jobs.run_job(state.id)


def test_jobs_require_markdown_and_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(jobs.JobInputError, match="require a Markdown"):
        jobs.create_job(SourceRequest(url="https://example.com"))

    monkeypatch.delenv("REDIS_URL", raising=False)
    with pytest.raises(jobs.JobsUnavailableError, match="REDIS_URL"):
        jobs.create_job(SourceRequest(markdown="# Page"))


def test_jobs_extra_is_loaded_only_when_used(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://example.com")
    jobs._redis_client_for_url.cache_clear()

    def missing_redis(_name: str) -> object:
        raise ModuleNotFoundError

    monkeypatch.setattr(jobs, "import_module", missing_redis)

    with pytest.raises(jobs.JobsUnavailableError, match=r"markdown-web\[jobs\]"):
        jobs.get_job("a" * 32)


def test_get_job_rejects_unknown_identifier(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_fake_redis(monkeypatch)

    with pytest.raises(jobs.JobNotFoundError, match="not found"):
        jobs.get_job("not-a-job")
