from markdown_web.bookmarklet import build_bookmarklets


def test_build_bookmarklets_use_server_key_and_endpoints() -> None:
    result = build_bookmarklets("https://markdown.example/", "temporary-key")

    assert result["markdown"].startswith("javascript:")
    assert result["telegraph"].startswith("javascript:")
    assert "https://markdown.example/md" in result["markdown"]
    assert "https://markdown.example/t" in result["telegraph"]
    assert "temporary-key" in result["markdown"]
    assert "TELEGRAPH_API_TOKEN" not in result["markdown"]
