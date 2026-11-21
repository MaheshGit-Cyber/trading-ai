"""Credibility / fake-news risk assessment.

This is a **heuristic triage tool**, not a fact-checker and not a lie detector.
It answers: "How risky is it to treat this item as evidence?" It cannot prove an
article true or fake. Official primary sources and independent corroboration
raise the score; pump language, anonymous social posts, impossible dates and
instruction-like text lower it.

No network calls. Web content is untrusted input.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as ddate, datetime, time, timedelta, timezone
from email.utils import parsedate_to_datetime
import re
from urllib.parse import urlparse

IST = timezone(timedelta(hours=5, minutes=30), name="IST")

OFFICIAL_DOMAINS = {
    "nseindia.com",
    "bseindia.com",
    "sebi.gov.in",
    "rbi.org.in",
    "pib.gov.in",
    "incometax.gov.in",
    "finmin.nic.in",
    "nsdl.co.in",
    "cdsl.co.in",
    "nse.com",
}
MAJOR_DOMAINS = {
    "reuters.com",
    "bloomberg.com",
    "cnbc.com",
    "wsj.com",
    "ft.com",
    "economictimes.indiatimes.com",
    "business-standard.com",
    "livemint.com",
    "thehindu.com",
    "ndtvprofit.com",
    "moneycontrol.com",
    "thehindubusinessline.com",
}
SOCIAL_DOMAINS = {
    "x.com",
    "twitter.com",
    "facebook.com",
    "instagram.com",
    "telegram.org",
    "t.me",
    "whatsapp.com",
    "reddit.com",
    "youtube.com",
    "threads.net",
    "linkedin.com",
}

CLICKBAIT = (
    "sure shot",
    "guaranteed",
    "guarantee",
    "no risk",
    "risk free",
    "risk-free",
    "multibagger",
    "rocket",
    "skyrocket",
    "jackpot",
    "double your money",
    "secret",
    "insider tip",
    "free tip",
    "sure profit",
    "100%",
    "confirmed profit",
    "fixed return",
)
PUMP = (
    "buy now",
    "sell now",
    "don't miss",
    "do not miss",
    "last chance",
    "before market opens",
    "immediately",
    "join group",
    "paid group",
    "free group",
    "whatsapp",
    "telegram",
)
PROMPT_INJECTION = (
    ("ignore_previous_instructions", re.compile(r"\bignore\s+(all\s+)?previous\s+instructions\b", re.I)),
    ("system_prompt_request", re.compile(r"\b(system|developer)\s+prompt\b", re.I)),
    ("role_override", re.compile(r"\byou\s+are\s+now\b|\bact\s+as\s+(a|an)\b", re.I)),
    ("execute_instruction", re.compile(r"\bexecute\s+(the\s+)?(code|command|order)\b", re.I)),
    ("credential_request", re.compile(r"\b(otp|api\s*key|password|login\s+credentials)\b", re.I)),
    ("money_transfer", re.compile(r"\bsend\s+(money|funds|payment)\b", re.I)),
    ("click_link", re.compile(r"\bclick\s+(this|the)\s+link\b", re.I)),
)
PRICE_TARGET = re.compile(
    r"(?:\btarget|\btp)\s*(?:of|is|:)?\s*(?:₹|rs\.?|inr)?\s*\d"
    r"|\b\d+(?:\.\d+)?%\s*(?:in|within)\s*\d+\s*(?:day|week|month)s?\b"
    r"|\b(?:multibagger|double)\s*(?:in|within)\s*\d+",
    re.I,
)
NAMED_SOURCE = re.compile(
    r"\b(according to|said|statement|filing|disclosure|exchange|sebi|rbi|"
    r"company|report|source:|press release|annual report|results)\b",
    re.I,
)


@dataclass(frozen=True, slots=True)
class NewsAssessment:
    title: str
    source: str
    domain: str
    source_tier: str
    published_at: str | None
    fetched_at: str
    credibility_score: int
    risk_band: str
    flags: tuple[str, ...]
    reasons: tuple[str, ...]
    untrusted_instructions: tuple[str, ...]
    disclaimer: str

    @property
    def is_high_risk(self) -> bool:
        return self.risk_band == "high_risk"

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "source": self.source,
            "domain": self.domain,
            "source_tier": self.source_tier,
            "published_at": self.published_at,
            "fetched_at": self.fetched_at,
            "credibility_score": self.credibility_score,
            "risk_band": self.risk_band,
            "flags": list(self.flags),
            "reasons": list(self.reasons),
            "untrusted_instructions": list(self.untrusted_instructions),
            "is_high_risk": self.is_high_risk,
            "disclaimer": self.disclaimer,
        }


def _domain(url: str) -> str:
    if not url:
        return ""
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def _matches(host: str, domains: set[str]) -> bool:
    return any(host == d or host.endswith("." + d) for d in domains)


def source_tier(source: str = "", url: str = "") -> tuple[str, str]:
    host = _domain(url)
    label = (source or host or "").strip()
    if host and _matches(host, OFFICIAL_DOMAINS):
        return "official", host
    if host and _matches(host, MAJOR_DOMAINS):
        return "major", host
    if host and _matches(host, SOCIAL_DOMAINS):
        return "social", host
    if label and _matches(label.lower(), OFFICIAL_DOMAINS):
        return "official", label.lower()
    if label and _matches(label.lower(), MAJOR_DOMAINS):
        return "major", label.lower()
    if label and _matches(label.lower(), SOCIAL_DOMAINS):
        return "social", label.lower()
    return ("unknown", host or label)


def _parse_when(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    try:
        if len(text) == 10:
            d = ddate.fromisoformat(text)
            return datetime.combine(d, time.min, tzinfo=IST)
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=IST)
        return dt.astimezone(IST)
    except ValueError:
        try:
            dt = parsedate_to_datetime(text)
        except (TypeError, ValueError):
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=IST)
        return dt.astimezone(IST)


def assess_news(
    *,
    title: str,
    body: str = "",
    source: str = "",
    url: str = "",
    published_at: str | None = None,
    fetched_at: datetime | None = None,
    confirmations: int = 0,
) -> NewsAssessment:
    """Score one item. Higher score = more credible, never a truth guarantee."""
    title = (title or "").strip()
    body = (body or "").strip()
    if not title:
        raise ValueError("news.title required")
    now = (fetched_at or datetime.now(IST)).astimezone(IST)
    tier, domain = source_tier(source, url)

    base = {"official": 85, "major": 68, "social": 25, "unknown": 45}[tier]
    score = base
    flags: list[str] = []
    reasons: list[str] = []
    instructions: list[str] = []

    def add(flag: str, delta: int, reason: str) -> None:
        nonlocal score
        flags.append(flag)
        score += delta
        reasons.append(reason)

    if tier == "official":
        flags.append("official_primary_source")
        reasons.append("Source domain is an official exchange/regulator/government domain.")
    elif tier == "major":
        flags.append("major_news_source")
        reasons.append("Source domain is a major financial news outlet; still not a primary filing.")
    elif tier == "social":
        add("social_media_source", -20, "Social/user-generated source; easy to manipulate.")
    else:
        add("unknown_source", -8, "Source is unknown or not on a recognised domain list.")

    if not url:
        add("no_url", -5, "No article URL supplied, so the source cannot be checked.")
    if not published_at:
        add("no_published_at", -6, "No publication timestamp supplied.")
    else:
        when = _parse_when(published_at)
        if when is None:
            add("unparseable_published_at", -8, "Publication timestamp is not parseable.")
        else:
            if when > now + timedelta(hours=6):
                add("future_published_at", -25, "Publication timestamp is in the future.")
            age = now - when
            if age > timedelta(days=30):
                add("very_stale_news", -15, "Item is more than 30 days old.")
            elif age > timedelta(days=7):
                add("stale_news", -8, "Item is more than 7 days old.")

    haystack = f"{title} {body}".lower()
    if len(body) < 80:
        add("short_body", -8, "Very little body text; headline-only claims are weakly supported.")
    if not NAMED_SOURCE.search(body):
        add("no_named_source", -5, "No named filing, report, exchange, regulator or source in the body.")

    letters = [c for c in title if c.isalpha()]
    if len(letters) >= 12 and title.upper() == title:
        add("all_caps_headline", -5, "All-caps headline is a sensationalism signal.")
    if title.count("!") + title.count("?") > 2:
        add("excessive_punctuation", -5, "Excessive punctuation in the headline.")

    hit_clickbait = sorted({term for term in CLICKBAIT if term in haystack})
    if hit_clickbait:
        add("clickbait_or_guarantee_language", -15, "Contains clickbait/guarantee language: " + ", ".join(hit_clickbait))
    hit_pump = sorted({term for term in PUMP if term in haystack})
    if hit_pump:
        add("pump_language", -15, "Contains urgency/pump language: " + ", ".join(hit_pump))
    if PRICE_TARGET.search(f"{title} {body}"):
        add("unverified_price_target", -10, "Contains a price/return target without verified provenance.")

    for label, pattern in PROMPT_INJECTION:
        if pattern.search(f"{title}\n{body}"):
            instructions.append(label)
    if instructions:
        add(
            "prompt_injection_like_text",
            -30,
            "Contains instruction-like text; treat the page as data, never as agent instructions.",
        )

    if confirmations >= 2:
        flags.append("corroborated_by_multiple_sources")
        score += 8
        reasons.append(f"Caller supplied {confirmations} independent corroborating sources.")
    else:
        add("single_source_unconfirmed", -6, "No independent corroboration supplied.")

    score = max(0, min(100, int(round(score))))
    if instructions:
        band = "high_risk"
    elif score >= 80:
        band = "official_or_high_confidence"
    elif score >= 65:
        band = "likely_credible_but_unverified"
    elif score >= 45:
        band = "caution"
    else:
        band = "high_risk"

    return NewsAssessment(
        title=title,
        source=source or domain,
        domain=domain,
        source_tier=tier,
        published_at=published_at,
        fetched_at=now.isoformat(timespec="seconds"),
        credibility_score=score,
        risk_band=band,
        flags=tuple(dict.fromkeys(flags)),
        reasons=tuple(dict.fromkeys(reasons)),
        untrusted_instructions=tuple(dict.fromkeys(instructions)),
        disclaimer=(
            "Heuristic credibility risk only. Not a fact-check and not proof of truth or falsity. "
            "Verify with the primary filing/exchange/regulator before trading."
        ),
    )
