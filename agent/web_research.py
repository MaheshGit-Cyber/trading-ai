"""Safe web/news research tools for the agent.

Powers:
  - fetch a public http(s) page (SSRF-guarded, size-limited)
  - extract title/description/text and publication metadata
  - search the web (DuckDuckGo HTML; best-effort, provider may block)
  - read Google News RSS for a query
  - attach the fake-news/credibility assessment

Web pages are untrusted data. Text from a page is never executed and never
treated as an instruction to the agent.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import html as html_lib
from html.parser import HTMLParser
import ipaddress
import re
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote_plus, unquote, urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from .news_guard import assess_news

IST = timezone(timedelta(hours=5, minutes=30), name="IST")
UA = "MahvexResearchAgent/0.1 (+research-only; no trading execution)"
MAX_BYTES = 1_000_000
ALLOWED_TYPES = (
    "text/html",
    "text/plain",
    "application/xhtml+xml",
    "application/xml",
    "text/xml",
    "application/rss+xml",
    "application/atom+xml",
)


class ResearchError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ResearchItem:
    title: str
    url: str
    snippet: str = ""
    source: str = ""
    published_at: str | None = None

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "source": self.source,
            "published_at": self.published_at,
        }


@dataclass(frozen=True, slots=True)
class FetchedPage:
    url: str
    final_url: str
    status: int
    content_type: str
    title: str
    description: str
    published_at: str | None
    text: str
    fetched_at: str
    truncated: bool
    assessment: dict | None = None

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "final_url": self.final_url,
            "status": self.status,
            "content_type": self.content_type,
            "title": self.title,
            "description": self.description,
            "published_at": self.published_at,
            "text": self.text,
            "fetched_at": self.fetched_at,
            "truncated": self.truncated,
            "assessment": self.assessment,
        }


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _embedded_ipv4(ip: ipaddress._BaseAddress) -> ipaddress.IPv4Address | None:
    """Extract IPv4 from NAT64/6to4 so an IPv6-only phone can reach public sites."""
    if ip.version != 6:
        return None
    value = int(ip)
    if ip in ipaddress.ip_network("64:ff9b::/96"):
        return ipaddress.IPv4Address(value & 0xFFFFFFFF)
    if ip in ipaddress.ip_network("64:ff9b:1::/48"):
        return ipaddress.IPv4Address(value & 0xFFFFFFFF)
    if ip in ipaddress.ip_network("2002::/16"):
        return ipaddress.IPv4Address((value >> 80) & 0xFFFFFFFF)
    return None


def _blocked_ip(ip: ipaddress._BaseAddress) -> bool:
    embedded = _embedded_ipv4(ip)
    if embedded is not None:
        return _blocked_ip(embedded)
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _validate_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ResearchError("only http/https URLs are allowed")
    if not parsed.hostname:
        raise ResearchError("URL has no hostname")
    if parsed.username or parsed.password:
        raise ResearchError("credentials in URL are not allowed")
    host = parsed.hostname
    if host.lower() in ("localhost", "localhost.localdomain"):
        raise ResearchError("localhost is blocked")
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as exc:
        raise ResearchError(f"cannot resolve host: {host}") from exc
    for info in infos:
        raw = info[4][0]
        try:
            ip = ipaddress.ip_address(raw.split("%")[0])
        except ValueError as exc:
            raise ResearchError(f"unparseable resolved address: {raw}") from exc
        if _blocked_ip(ip):
            raise ResearchError(f"private/reserved address blocked: {raw}")


def _decode(body: bytes, content_type: str) -> str:
    charset = "utf-8"
    m = re.search(r"charset=([\w-]+)", content_type or "", re.I)
    if m:
        charset = m.group(1)
    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.meta: dict[str, str] = {}
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in ("script", "style", "noscript", "svg", "canvas"):
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "meta":
            values = {k.lower(): (v or "") for k, v in attrs}
            key = (values.get("property") or values.get("name") or "").lower()
            content = values.get("content") or ""
            if key and content:
                self.meta.setdefault(key, content)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in ("script", "style", "noscript", "svg", "canvas") and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        if self._in_title:
            self.title_parts.append(data)
        self.text_parts.append(data)


def extract_page(html: str) -> tuple[str, str, str | None, str]:
    parser = _PageParser()
    parser.feed(html or "")
    title = _clean(" ".join(parser.title_parts))
    description = _clean(
        parser.meta.get("description")
        or parser.meta.get("og:description")
        or parser.meta.get("twitter:description")
        or ""
    )
    published = (
        parser.meta.get("article:published_time")
        or parser.meta.get("date")
        or parser.meta.get("pubdate")
        or parser.meta.get("publish-date")
        or None
    )
    text = _clean(" ".join(parser.text_parts))
    if len(text) > 20_000:
        text = text[:20_000] + " …[truncated]"
    return title, description, published, text


def parse_search_html(html: str) -> list[ResearchItem]:
    """Parse DuckDuckGo HTML results. Fixture-testable, provider may change HTML."""
    anchors: list[tuple[int, str, str]] = []
    for m in re.finditer(r"<a\b([^>]*)>(.*?)</a>", html or "", re.S | re.I):
        attrs, inner = m.group(1), m.group(2)
        cls = re.search(r'class\s*=\s*"([^"]*)"', attrs, re.I)
        href = re.search(r'href\s*=\s*"([^"]*)"', attrs, re.I)
        if not cls or "result__a" not in cls.group(1).lower() or not href:
            continue
        url = html_lib.unescape(href.group(1))
        if url.startswith("/l/") or "uddg=" in url:
            q = parse_qs(urlparse(url).query)
            if q.get("uddg"):
                url = unquote(q["uddg"][0])
        anchors.append((m.start(), url, _clean(inner)))
    out: list[ResearchItem] = []
    for i, (pos, url, title) in enumerate(anchors):
        end = anchors[i + 1][0] if i + 1 < len(anchors) else len(html)
        block = html[pos:end]
        snip = re.search(
            r'class\s*=\s*"[^"]*result__snippet[^"]*"[^>]*>(.*?)</(?:a|div|span)>',
            block,
            re.S | re.I,
        )
        snippet = _clean(snip.group(1)) if snip else ""
        out.append(
            ResearchItem(
                title=title,
                url=url,
                snippet=snippet,
                source=urlparse(url).hostname or "",
            )
        )
    return out


def _decode_bing_url(url: str) -> str:
    """Bing wraps result links in /ck/a?...&u=a1<base64-url>."""
    if "bing.com/ck/a" not in url:
        return url
    query = parse_qs(urlparse(url).query)
    raw = (query.get("u") or [""])[0]
    if not raw:
        return url
    data = raw[2:] if raw.startswith("a1") else raw
    data += "=" * (-len(data) % 4)
    try:
        decoded = base64.urlsafe_b64decode(data.encode("ascii")).decode("utf-8")
    except Exception:
        return url
    return decoded if decoded.startswith(("http://", "https://")) else url


def parse_bing_html(html: str) -> list[ResearchItem]:
    out: list[ResearchItem] = []
    for block in re.findall(r'<li class="b_algo".*?</li>', html or "", re.S | re.I):
        h2 = re.search(r"<h2[^>]*>(.*?)</h2>", block, re.S | re.I)
        if not h2:
            continue
        href = re.search(r'href="([^"]+)"', h2.group(1), re.I)
        if not href:
            continue
        url = html_lib.unescape(href.group(1))
        url = _decode_bing_url(url)
        title = _clean(h2.group(1))
        snippet = ""
        p = re.search(r"<p[^>]*>(.*?)</p>", block, re.S | re.I)
        if p:
            snippet = _clean(p.group(1))
        out.append(
            ResearchItem(
                title=title,
                url=url,
                snippet=snippet,
                source=urlparse(url).hostname or "",
            )
        )
    return out


class WebResearch:
    def __init__(self, *, timeout: float = 15.0, max_bytes: int = MAX_BYTES):
        self.timeout = timeout
        self.max_bytes = max_bytes

    def _http_get(self, url: str) -> tuple[str, int, str, bytes, bool]:
        _validate_public_url(url)
        req = Request(
            url,
            headers={
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml,application/xml,text/plain;q=0.9,*/*;q=0.1",
            },
        )
        try:
            with urlopen(req, timeout=self.timeout) as response:
                final = response.geturl()
                _validate_public_url(final)
                status = getattr(response, "status", 200)
                ctype = response.headers.get("Content-Type", "")
                raw = response.read(self.max_bytes + 1)
                truncated = len(raw) > self.max_bytes
                if truncated:
                    raw = raw[: self.max_bytes]
                if not any(ctype.lower().startswith(t) for t in ALLOWED_TYPES):
                    raise ResearchError(f"unsupported content type: {ctype or 'unknown'}")
                return final, status, ctype, raw, truncated
        except HTTPError as exc:
            raise ResearchError(f"HTTP {exc.code} for {url}") from exc
        except URLError as exc:
            raise ResearchError(f"network error for {url}: {exc.reason}") from exc

    def fetch(self, url: str, *, assess: bool = False) -> FetchedPage:
        final, status, ctype, raw, truncated = self._http_get(url)
        text = _decode(raw, ctype)
        title, description, published, body = extract_page(text)
        page = FetchedPage(
            url=url,
            final_url=final,
            status=status,
            content_type=ctype,
            title=title,
            description=description,
            published_at=published,
            text=body,
            fetched_at=datetime.now(IST).isoformat(timespec="seconds"),
            truncated=truncated,
        )
        if not assess:
            return page
        a = assess_news(
            title=title or url,
            body=body,
            source=urlparse(final).hostname or "",
            url=final,
            published_at=published,
        )
        return FetchedPage(
            url=page.url,
            final_url=page.final_url,
            status=page.status,
            content_type=page.content_type,
            title=page.title,
            description=page.description,
            published_at=page.published_at,
            text=page.text,
            fetched_at=page.fetched_at,
            truncated=page.truncated,
            assessment=a.to_dict(),
        )

    def assess_url(self, url: str) -> dict:
        page = self.fetch(url, assess=False)
        a = assess_news(
            title=page.title or url,
            body=page.text,
            source=urlparse(page.final_url).hostname or "",
            url=page.final_url,
            published_at=page.published_at,
        )
        out = page.to_dict()
        out["assessment"] = a.to_dict()
        return out

    def search(self, query: str, *, max_results: int = 5) -> list[ResearchItem]:
        if not query.strip():
            raise ValueError("search query required")
        max_results = max(1, max_results)
        errors: list[str] = []
        # Bing first: DuckDuckGo HTML often returns an HTTP 202 challenge.
        for engine_url, parser in (
            ("https://www.bing.com/search?q=" + quote_plus(query), parse_bing_html),
            ("https://lite.duckduckgo.com/lite/?q=" + quote_plus(query), parse_search_html),
        ):
            try:
                _final, _status, ctype, raw, _trunc = self._http_get(engine_url)
                items = parser(_decode(raw, ctype))
                if items:
                    return items[:max_results]
            except ResearchError as exc:
                errors.append(str(exc))
        if errors:
            raise ResearchError("search failed: " + " | ".join(errors))
        return []

    def news(self, query: str, *, max_results: int = 10) -> list[ResearchItem]:
        if not query.strip():
            raise ValueError("news query required")
        url = (
            "https://news.google.com/rss/search?q="
            + quote_plus(query)
            + "&hl=en-IN&gl=IN&ceid=IN:en"
        )
        _final, _status, ctype, raw, _trunc = self._http_get(url)
        try:
            root = ET.fromstring(_decode(raw, ctype))
        except ET.ParseError as exc:
            raise ResearchError("news RSS parse failed") from exc
        out: list[ResearchItem] = []
        for item in root.findall(".//item"):
            title = _clean(item.findtext("title") or "")
            link = (item.findtext("link") or "").strip()
            pub = (item.findtext("pubDate") or "").strip() or None
            source = ""
            src_el = item.find("source")
            if src_el is not None and src_el.text:
                source = _clean(src_el.text)
            if title and link:
                out.append(ResearchItem(title=title, url=link, source=source, published_at=pub))
            if len(out) >= max_results:
                break
        return out
