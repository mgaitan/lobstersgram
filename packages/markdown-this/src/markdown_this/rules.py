"""Small declarative extraction rules for high-value domains."""

from __future__ import annotations

import urllib.parse
from collections.abc import Iterable
from dataclasses import dataclass
from logging import getLogger

from bs4 import BeautifulSoup
from soupsieve import SelectorSyntaxError

logger = getLogger(__name__)


@dataclass(frozen=True)
class DomainRule:
    hosts: tuple[str, ...]
    body_selectors: tuple[str, ...]
    strip_selectors: tuple[str, ...] = ()


DOMAIN_RULES: tuple[DomainRule, ...] = (
    DomainRule(
        hosts=("substack.com",),
        body_selectors=(".available-content",),
        strip_selectors=(".image-link-expand",),
    ),
)


def apply_domain_rule(
    content_html: str,
    url: str,
    rules: Iterable[DomainRule] = DOMAIN_RULES,
) -> str | None:
    """Return selected HTML for a URL when a declarative rule matches."""
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    if not host:
        return None

    rule = next(
        (
            rule
            for rule in rules
            if any(host == candidate or host.endswith(f".{candidate}") for candidate in rule.hosts)
        ),
        None,
    )
    if rule is None:
        return None

    soup = BeautifulSoup(content_html, "html.parser")
    try:
        for selector in rule.body_selectors:
            body = soup.select_one(selector)
            if body is None:
                continue
            for strip in rule.strip_selectors:
                for element in body.select(strip):
                    element.decompose()
            if body.get_text(strip=True):
                return str(body)
    except SelectorSyntaxError as exc:
        logger.warning("domain rule selector failed error=%s", exc)
    return None
