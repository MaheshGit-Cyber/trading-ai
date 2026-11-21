#!/usr/bin/env python3
"""Safe web parsing and SSRF tests (offline; no real network)."""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agent.web_research import (  # noqa: E402
    ResearchError,
    _validate_public_url,
    extract_page,
    parse_bing_html,
    parse_search_html,
)

PASS = 0
FAIL = 0


def ok(name: str, fn) -> None:
    global PASS, FAIL
    try:
        fn()
        PASS += 1
        print(f"  PASS  {name}")
    except Exception as exc:
        FAIL += 1
        print(f"  FAIL  {name}: {exc}")


def test_ssrf_blocks() -> None:
    for url in (
        "file:///etc/passwd",
        "http://localhost/",
        "http://127.0.0.1/",
        "http://[::1]/",
        "http://0.0.0.0/",
    ):
        try:
            _validate_public_url(url)
        except ResearchError:
            continue
        raise AssertionError(f"blocked URL accepted: {url}")


def test_extract_page() -> None:
    html = """
    <html><head>
      <title>NSE circular</title>
      <meta name="description" content="A test description">
      <meta property="article:published_time" content="2026-11-20T18:00:00+05:30">
    </head><body>
      <script>ignore me</script>
      <p>SEBI said the settlement cycle remains T+1.</p>
    </body></html>
    """
    title, desc, published, text = extract_page(html)
    assert title == "NSE circular"
    assert desc == "A test description"
    assert published.startswith("2026-11-20")
    assert "T+1" in text
    assert "ignore me" not in text


def test_parse_search() -> None:
    html = """
    <a rel="nofollow" class="result__a" href="https://example.com/a">Title A</a>
    <a class="result__snippet" href="#">Snippet A</a>
    <a class="result__a" href="/l/?uddg=https%3A%2F%2Fexample.com%2Fb">Title B</a>
    <div class="result__snippet">Snippet B</div>
    """
    items = parse_search_html(html)
    assert [i.title for i in items] == ["Title A", "Title B"]
    assert items[0].url == "https://example.com/a"
    assert items[1].url == "https://example.com/b"
    assert "Snippet" in items[0].snippet


def test_parse_bing() -> None:
    import base64
    target = "https://www.nseindia.com/all-reports"
    encoded = "a1" + base64.urlsafe_b64encode(target.encode()).decode().rstrip("=")
    html = f"""
    <li class="b_algo"><h2><a href="https://www.bing.com/ck/a?u={encoded}">
      <strong>All Reports</strong> - NSE India</a></h2>
      <p>Get latest reports from the exchange.</p></li>
    """
    items = parse_bing_html(html)
    assert len(items) == 1
    assert items[0].url == target
    assert items[0].title == "All Reports - NSE India"
    assert "latest reports" in items[0].snippet


def main() -> None:
    print("web research:")
    ok("SSRF blocks", test_ssrf_blocks)
    ok("page extraction", test_extract_page)
    ok("search parsing", test_parse_search)
    ok("Bing parsing", test_parse_bing)
    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
