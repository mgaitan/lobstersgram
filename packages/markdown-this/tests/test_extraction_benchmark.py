"""Offline quality benchmark cases for real-world extraction failures."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from markdown_this import extract_main_content, markdown_to_text, split_front_matter

FIXTURES = Path(__file__).parent / "fixtures" / "extraction"
CASES_FILE = FIXTURES / "cases.yaml"


def _load_cases() -> list[pytest.ParameterSet]:
    data = yaml.safe_load(CASES_FILE.read_text(encoding="utf-8"))
    cases = data["cases"]
    params = []
    for case in cases:
        marks = []
        if reason := case.get("xfail"):
            marks.append(pytest.mark.xfail(reason=reason, strict=True))
        params.append(pytest.param(case, id=case["id"], marks=marks))
    return params


@pytest.mark.parametrize("case", _load_cases())
def test_extraction_quality_case(case: dict[str, Any]) -> None:
    title, markdown, fallback_text, intro = extract_main_content(FIXTURES / case["fixture"], min_content_length=0)
    metadata, _body = split_front_matter(markdown)
    plain_text = markdown_to_text(markdown)
    haystack = "\n".join((title, markdown, fallback_text, intro, plain_text))

    for field, expected in case.get("metadata", {}).items():
        assert metadata.get(field) == expected

    for phrase in case.get("contains", []):
        assert phrase in haystack

    for phrase in case.get("not_contains", []):
        assert phrase not in haystack

    assert len(plain_text) >= case.get("min_text_chars", 0)
