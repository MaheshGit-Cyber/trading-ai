"""Evidence layer: rules + memory + RAG -> model -> validated evidence.

This is the part people call "training". It is not weight training.
It is teaching at inference time:

    rules.json      -> what the system believes (versioned, auditable)
    memory.jsonl    -> what it has seen before (append-only)
    rag/index.json  -> domain knowledge (retrieved, verbatim)

Those three survive a model swap. The weights do not exist to keep.

Failure policy is explicit: retry up to 3 times, then FALL BACK to
Layer-3 alone. A bad model reply is dropped, never passed downstream.
"""

from __future__ import annotations

import json
import os
import time

from . import paths, rag, schema

SYSTEM = """You are the evidence analyst for a signal-only trading system.

You have exactly one job: read the structured inputs you are given and
return a single scored JSON object.

Hard rules:
- Never output a price, a price target, or any numeric forecast of price.
- Never output an instruction to buy or sell. A separate deterministic
  gate owns that decision; you do not have that authority.
- Score only from the data provided. Do not import outside tickers or
  outside news.
- The Devil's Advocate field is mandatory: state the strongest honest
  case AGAINST this signal. A one-sided note is a failed reply.
- Output exactly one JSON object and nothing else. No markdown fences,
  no preamble, no closing commentary.

Output contract:
{
  "symbol": str,
  "direction": "up" | "down" | "flat",
  "regime": echo the Layer-3 regime label exactly (trend_up | trend_down |
            range | transition | unknown). Do not reclassify it.
  "scores": {"momentum": 0-4, "trend": 0-4, "structure": 0-4,
             "volume": 0-4, "regime": 0-4},
  "weighted_total": number,
  "devils_advocate": str (>= 20 chars),
  "notes": str
}

weighted_total MUST equal the sum of
  scores[k] * rules.evidence_weights[k] over all five keys.
It will be recomputed and checked. Do not invent arithmetic.

confidence_band is computed by the deterministic gate from weighted_total
and rules.band_thresholds. Do not output it; the gate owns that label.

Operational constraints (from knowledge/*.json -- never contradict these):
- No signal when: the stock is in the F&O ban list, earnings fall inside
  the horizon, a circuit limit was hit in the last 3 sessions, the data is
  older than one session, or a corporate action falls inside the horizon.
- Round-trip costs before slippage, per Rs 1,00,000: equity intraday 8.25 bps,
  delivery 23.58 bps, futures 10.35 bps, options 28.31 bps. Costs are not zero.
- Minimum reward:risk is 2.0 with no per-setup exception. Minimum sample
  before claiming an edge is 100 closed trades.
- Every signal must name at least one concrete failure mode for its setup.
  "Markets can go down" is a failed reply.
"""


def load_rules() -> dict:
    with open(paths.RULES, "r", encoding="utf-8") as f:
        rules = json.load(f)
    return schema.validate_rules(rules)


def load_memory() -> list[dict]:
    if not os.path.exists(paths.MEMORY):
        return []
    out: list[dict] = []
    with open(paths.MEMORY, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                # Corrupt line: report, do not silently skip.
                raise SystemExit(f"memory.jsonl line {i} is not valid JSON: {e}") from e
            out.append(schema.validate_memory_line(obj))
    return out


def memory_hits(events: list[dict], symbol: str, k: int = 6) -> list[dict]:
    """Same-symbol first, then recency. No embeddings -- the log is small.

    `events` is oldest-first. The old `(sym + rest)[-k:]` looked right but
    dropped every same-symbol event once there were k other-symbol events:
    the tail only contained `rest`. Keep the same-symbol tail, then fill the
    remaining slots with the most recent other symbols.
    """
    if k <= 0:
        return []
    sym = [e for e in events if e.get("symbol") == symbol]
    rest = [e for e in events if e.get("symbol") != symbol]
    if len(sym) >= k:
        return sym[-k:]
    return sym + rest[-(k - len(sym)):]


def append_memory(obj: dict) -> None:
    """Append-only write. Validates first; never rewrites existing lines."""
    schema.validate_memory_line(obj)
    os.makedirs(os.path.dirname(paths.MEMORY), exist_ok=True)
    with open(paths.MEMORY, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _prompt(rules: dict, mem: list[dict], chunks: list[dict], layer3: dict) -> str:
    parts: list[str] = []

    parts.append("## rules.json (behaviour you must follow)\n"
                 + json.dumps(rules, ensure_ascii=False, indent=2))

    if mem:
        lines = "\n".join(json.dumps(m, ensure_ascii=False) for m in mem)
        parts.append(f"## Relevant past memory ({len(mem)} events, oldest first)\n{lines}")
    else:
        parts.append("## Relevant past memory\n(none yet -- this is an early event)")

    if chunks:
        blocks = []
        for c in chunks:
            blocks.append(f"### {c['src']} :: {c['title']}\n{c['text']}")
        parts.append(
            f"## Retrieved knowledge ({len(chunks)} chunks, quoted verbatim)\n"
            + "\n\n".join(blocks)
        )
    else:
        parts.append("## Retrieved knowledge\n(none retrieved)")

    parts.append("## Layer-3 prediction input (statistical, already computed)\n"
                 + json.dumps(layer3, ensure_ascii=False, indent=2))

    parts.append("Return exactly one JSON object matching the output contract.")
    return "\n\n".join(parts)


def _fallback(layer3: dict, reason: str) -> dict:
    """What the gate sees when the evidence layer fails.

    Scores are all 0 -- deliberately. Zero evidence must not look like
    strong evidence, so the deterministic gate is left with Layer-3 only
    and will normally decline to emit a signal.
    """
    return {
        "symbol": layer3.get("symbol", "UNKNOWN"),
        "direction": layer3.get("direction", "flat"),
        "regime": layer3.get("regime", "unknown"),
        "confidence_band": "low",
        "scores": {k: 0 for k in schema.SCORE_KEYS},
        "weighted_total": 0,
        "devils_advocate": "evidence layer unavailable: " + reason,
        "notes": "FALLBACK -- no model evidence. Gate must rely on Layer-3 alone.",
        "_fallback": True,
        "_fallback_reason": reason,
    }


def run(layer3: dict, provider: str | None = None, k_rag: int = 4,
        max_attempts: int = 3, verbose: bool = True) -> dict:
    """Produce validated evidence for one Layer-3 prediction."""
    from adapters.base import get_adapter  # trading-ai/ is on sys.path

    rules = load_rules()
    events = load_memory()

    symbol = layer3.get("symbol", "")
    question = " ".join([
        symbol,
        str(layer3.get("features") or ""),
        str(layer3.get("regime") or ""),
        str(layer3.get("horizon") or ""),
        "risk management position sizing regime trend range",
    ])

    chunks: list[dict] = []
    if os.path.exists(paths.RAG_INDEX):
        try:
            chunks = rag.query(rag.load(paths.RAG_INDEX), question, k=k_rag)
        except Exception as e:  # RAG failure must not kill the run
            if verbose:
                print(f"[rag] query failed: {e}")

    mem = memory_hits(events, symbol)
    user = _prompt(rules, mem, chunks, layer3)

    with open(paths.CONFIG, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    adapter = get_adapter(cfg, provider)

    errors: list[str] = []
    for attempt in range(1, max_attempts + 1):
        t0 = time.time()
        try:
            raw = adapter.complete(SYSTEM, user)
        except Exception as e:
            errors.append(f"attempt {attempt}: transport: {e}")
            if verbose:
                print(f"[evidence] attempt {attempt} transport error: {e}")
            continue
        try:
            obj = schema.extract_json(raw)
            ev = schema.validate_evidence(obj, rules)
            # Regime is computed by the engine, never by the model. Echo the
            # engine label and record any disagreement instead of honouring it.
            engine_regime = layer3.get("regime")
            if engine_regime and ev.get("regime") != engine_regime:
                ev["_regime_overridden"] = ev.get("regime")
                ev["regime"] = engine_regime
            ev["_attempts"] = attempt
            ev["_latency_s"] = round(time.time() - t0, 2)
            ev["_provider"] = provider or cfg.get("active")
            if verbose:
                print(f"[evidence] ok on attempt {attempt} "
                      f"({ev['_latency_s']}s) total={ev['weighted_total']}")
            return ev
        except schema.SchemaError as e:
            errors.append(f"attempt {attempt}: schema: {e}")
            if verbose:
                print(f"[evidence] attempt {attempt} schema rejected: {e}")

    if verbose:
        print("[evidence] exhausted retries -> FALLBACK (Layer-3 only)")
    return _fallback(layer3, "; ".join(errors[-3:]) or "no provider configured")
