"""Deterministic validation gate.

Design rules (these are not negotiable):

1. Every artifact is validated BEFORE it is written.
2. LLM output that fails validation never reaches the decision layer.
   It is retried, then dropped to a fallback that uses Layer-3 alone.
3. The evidence layer may not contain a price target or a trade
   instruction -- that authority belongs to the deterministic gate,
   and to the human.

Stdlib only. No numpy, no pydantic.
"""

from __future__ import annotations

import json
import re

DIRECTIONS = ("up", "down", "flat")
REGIMES = ("trend", "trend_up", "trend_down", "range", "transition", "unknown")
BANDS = ("low", "medium", "high")
SCORE_KEYS = ("momentum", "trend", "structure", "volume", "regime")
SCORE_MAX = 4.0
MEMORY_KINDS = ("event", "outcome", "demo", "note")
DEFAULT_BAND_THRESHOLDS = {"high": 0.75, "medium": 0.50}

# The gate cannot verify that the Devil's Advocate names a failure mode from
# failures.json without knowing the setup. It CAN reject the literal cop-outs
# the knowledge file calls out. Exact-match only -- no false positives on a
# specific note that happens to mention the market.
_GENERIC_DA = {
    "markets can go down", "market can go down",
    "prices can go down", "price can go down",
    "stocks can go down", "stock can go down",
    "anything can happen", "no guarantee", "no guarantees",
    "risk exists", "markets are risky", "trading is risky",
}

# Content guard: the evidence layer must not issue prices or trade instructions.
_FORBIDDEN = re.compile(
    r"(?<![\w.])\u20b9\s?\d"
    r"|\b(?:target price|price target|buy now|sell now|enter (?:long|short)|"
    r"go long|go short|place (?:a )?(?:buy|sell) order|"
    r"we predict[^.]{0,40}will (?:reach|hit))\b",
    re.IGNORECASE,
)


class SchemaError(ValueError):
    """Raised when an artifact does not conform to its contract."""


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise SchemaError(msg)


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _da_norm(s: str) -> str:
    """Lowercase, collapse whitespace, strip trailing punctuation."""
    s = re.sub(r"\s+", " ", s.strip().lower())
    return re.sub(r"[\s.!]+$", "", s)


def validate_rules(obj: dict) -> dict:
    """Behaviour config. Bump 'version' on every edit; commit to git."""
    _require(isinstance(obj, dict), "rules must be a JSON object")
    _require(isinstance(obj.get("version"), int) and obj["version"] >= 1,
             "rules.version must be an int >= 1")
    _require(_is_num(obj.get("min_rr")) and obj["min_rr"] >= 1,
             "rules.min_rr must be a number >= 1")
    _require(_is_num(obj.get("max_position_pct")) and 0 < obj["max_position_pct"] <= 100,
             "rules.max_position_pct must be in (0, 100]")
    _require(isinstance(obj.get("evidence_weights"), dict),
             "rules.evidence_weights must be an object")
    for k in SCORE_KEYS:
        _require(k in obj["evidence_weights"], f"rules.evidence_weights missing '{k}'")
        _require(_is_num(obj["evidence_weights"][k]),
                 f"rules.evidence_weights.{k} must be a number")
    _require(isinstance(obj.get("devils_advocate"), str),
             "rules.devils_advocate must be a string")
    bt = obj.get("band_thresholds", DEFAULT_BAND_THRESHOLDS)
    _require(isinstance(bt, dict), "rules.band_thresholds must be an object")
    for k in ("high", "medium"):
        _require(_is_num(bt.get(k)), f"rules.band_thresholds.{k} must be a number")
        _require(0 < bt[k] <= 1, f"rules.band_thresholds.{k} must be in (0, 1]")
    _require(bt["high"] > bt["medium"],
             "rules.band_thresholds.high must be greater than medium")
    _require(isinstance(obj.get("learning"), dict) and
             obj["learning"].get("auto_learn") is False,
             "rules.learning.auto_learn must be false -- no automatic promotion")
    return obj


def validate_memory_line(obj: dict) -> dict:
    """One line of memory.jsonl. Append-only: never edit an existing line."""
    _require(isinstance(obj, dict), "memory line must be a JSON object")
    _require(isinstance(obj.get("ts"), str) and obj["ts"],
             "memory.ts required (ISO-8601 string)")
    _require(obj.get("kind") in MEMORY_KINDS,
             f"memory.kind must be one of {MEMORY_KINDS}")

    if obj["kind"] == "outcome":
        _require(isinstance(obj.get("ref"), str) and obj["ref"],
                 "outcome requires 'ref' pointing at the event it closes")
        _require(_is_num(obj.get("r_multiple")),
                 "outcome.r_multiple must be a number (can be negative)")
        _require(obj.get("verdict") in ("win", "loss", "scratch"),
                 "outcome.verdict must be win|loss|scratch")
    elif obj["kind"] in ("event", "demo"):
        _require(isinstance(obj.get("symbol"), str) and obj["symbol"],
                 "event.symbol required")
        _require(isinstance(obj.get("evidence"), dict),
                 "event.evidence must be the validated evidence object")
        # The validated evidence must still satisfy the evidence contract.
        _require("scores" in obj["evidence"] and "weighted_total" in obj["evidence"],
                 "event.evidence missing scores/weighted_total")
    return obj


def validate_evidence(obj: dict, rules: dict) -> dict:
    """The LLM output contract. Fails -> retry -> fallback to Layer-3 only."""
    _require(isinstance(obj, dict),
             "evidence must be exactly one JSON object (no markdown, no prose)")

    _require(isinstance(obj.get("symbol"), str) and obj["symbol"],
             "evidence.symbol required")
    _require(obj.get("direction") in DIRECTIONS,
             f"evidence.direction must be one of {DIRECTIONS}")
    _require(obj.get("regime") in REGIMES,
             f"evidence.regime must be one of {REGIMES}")
    # confidence_band is computed below. Accept a model-supplied value only
    # to record the disagreement; never trust it as the label.
    _require(obj.get("confidence_band") is None or
             obj.get("confidence_band") in BANDS,
             f"evidence.confidence_band, if present, must be one of {BANDS}")

    scores = obj.get("scores")
    _require(isinstance(scores, dict), "evidence.scores must be an object")

    weights = rules["evidence_weights"]
    recomputed = 0.0
    for k in SCORE_KEYS:
        _require(k in scores, f"evidence.scores missing '{k}'")
        v = scores[k]
        _require(_is_num(v), f"evidence.scores.{k} must be a number")
        _require(0 <= v <= SCORE_MAX,
                 f"evidence.scores.{k} must be in [0, {SCORE_MAX}]")
        recomputed += float(v) * float(weights[k])

    reported = obj.get("weighted_total")
    _require(_is_num(reported), "evidence.weighted_total must be a number")
    # Anti-hallucination: the model must not invent its own arithmetic.
    _require(abs(float(reported) - recomputed) <= 0.01,
             f"evidence.weighted_total {reported} != recomputed {round(recomputed, 3)} "
             f"-- recompute from scores and rules.evidence_weights")

    # The band is a deterministic function of weighted_total, not a model
    # opinion. Same rule as regime: the model may not assign the label.
    bt = rules.get("band_thresholds") or DEFAULT_BAND_THRESHOLDS
    max_total = SCORE_MAX * sum(float(weights[k]) for k in SCORE_KEYS)
    frac = (recomputed / max_total) if max_total > 0 else 0.0
    band = ("high" if frac >= float(bt["high"])
            else "medium" if frac >= float(bt["medium"])
            else "low")
    reported_band = obj.get("confidence_band")
    if reported_band is not None and reported_band != band:
        obj["_band_overridden"] = reported_band
    obj["confidence_band"] = band

    da = obj.get("devils_advocate")
    _require(isinstance(da, str) and len(da.strip()) >= 20,
             "evidence.devils_advocate required and must be >= 20 characters "
             "(the strongest case AGAINST this signal)")
    _require(_da_norm(da) not in _GENERIC_DA,
             "evidence.devils_advocate is a generic cop-out -- name the "
             "concrete failure mode that would invalidate this signal")

    blob = json.dumps(obj, ensure_ascii=False)
    _require(not _FORBIDDEN.search(blob),
             "evidence contains a price target or a trade instruction -- "
             "forbidden in the evidence layer")
    return obj


def extract_json(text: str) -> dict:
    """Pull the first balanced JSON object out of an LLM reply."""
    if not isinstance(text, str) or not text.strip():
        raise SchemaError("empty model reply")
    t = text.strip()
    # Strip ```json fences if present.
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    start = t.find("{")
    if start < 0:
        raise SchemaError("no JSON object found in model reply")
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(t)):
        c = t[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(t[start:i + 1])
                except json.JSONDecodeError as e:
                    raise SchemaError(f"malformed JSON: {e}") from e
                if not isinstance(obj, dict):
                    raise SchemaError("top-level JSON must be an object")
                return obj
    raise SchemaError("unbalanced JSON object in model reply")
