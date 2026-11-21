"""Retrieval over the local course corpus. Pure Python -- no numpy, no embeddings.

Why BM25 and not vector embeddings:
  * No embedding model is installed and none can run offline at quality.
  * The corpus is ~50 markdown files. Keyword retrieval is sufficient and
    is fully deterministic, which matters more here than recall.

Chunking rule: split markdown on headings. Never re-write a chunk --
retrieval returns source text verbatim so it can be audited.

Two lessons from eval/retrieval_eval.py (first version scored hit@5 = 79%):
  1. Every sub-chunk must carry its section heading. Without it, later
     pieces of a long section were unidentifiable.
  2. Heading terms must be weighted above body terms. Crisis sections share
     almost all their vocabulary ("peak", "bottom", "recovery"), so body-only
     BM25 cannot tell 2000 from 2008. The heading is the discriminator.
"""

from __future__ import annotations

import json
import math
import os
import re
import time

K1 = 1.5
B = 0.75
TITLE_WEIGHT = 3.0
MAX_CHUNK_CHARS = 1500
MIN_CHUNK_CHARS = 40

_STOP = set(
    """a an the and or but if then of in on at to for with from by as is are was
    were be been being this that these those it its our your we you they he she
    i not no nor so than too very can will just about into over under again
    further once here when where why how all any both each few more most other
    some such only own same do does did doing have has had having""".split()
)
_TOKEN = re.compile(r"[a-z0-9]+")
_HEADING = re.compile(r"^(#{1,4})\s+(.*)$")


def _stem(t: str) -> str:
    """Plural-only stemmer. Deliberately crude, deliberately deterministic.

    Without it 'regime' does not match 'regimes', and the operational
    regime table loses to any prose paragraph that says 'regime'.
    """
    if len(t) > 4 and t.endswith("s") and not t.endswith("ss"):
        return t[:-1]
    return t


def _tokens(s: str) -> list[str]:
    return [_stem(t) for t in _TOKEN.findall(s.lower())
            if len(t) > 1 and t not in _STOP]


def _split_sections(text: str) -> list[tuple[str, str]]:
    """-> [(heading_path, body)] with heading_path like '07-risk > Position Sizing'."""
    sections: list[tuple[str, str]] = []
    path: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        body = "\n".join(buf).strip()
        if len(body) >= MIN_CHUNK_CHARS:
            sections.append((" > ".join(path) if path else "(preamble)", body))
        buf.clear()

    for line in text.splitlines():
        m = _HEADING.match(line)
        if m:
            flush()
            level = len(m.group(1))
            title = m.group(2).strip()
            path[level - 1:] = [title]
            buf.append(title)
        else:
            buf.append(line)
    flush()
    return sections


def _subchunk(body: str, limit: int = MAX_CHUNK_CHARS) -> list[str]:
    """Hard-split oversized sections on paragraph boundaries."""
    if len(body) <= limit:
        return [body]
    out: list[str] = []
    cur: list[str] = []
    size = 0
    for para in body.split("\n\n"):
        if size + len(para) > limit and cur:
            out.append("\n\n".join(cur))
            cur, size = [], 0
        cur.append(para)
        size += len(para)
    if cur:
        out.append("\n\n".join(cur))
    return out


def _scalar_lines(obj, prefix: str = "") -> list[str]:
    """Flatten nested JSON into 'key: value' lines so BM25 can read it."""
    lines: list[str] = []
    for k, v in obj.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            lines.extend(_scalar_lines(v, key + "."))
        elif isinstance(v, list):
            if v and isinstance(v[0], dict):
                for i, item in enumerate(v):
                    flat = "; ".join(
                        f"{kk}={vv}" for kk, vv in item.items()
                        if not isinstance(vv, (dict, list))
                    )
                    lines.append(f"{key}[{i}]: {flat}")
            else:
                lines.append(f"{key}: {'; '.join(str(x) for x in v)}")
        else:
            lines.append(f"{key}: {v}")
    return lines


def _json_sections(path: str) -> list[tuple[str, str]]:
    """Turn an operational JSON file into (heading, body) sections.

    Nested dicts are split into their own sections rather than flattened
    into one blob. Without that, 'adj_factor' hides inside a 40-line
    'corporate_actions' dump and loses to any prose paragraph that happens
    to mention 'split'.
    """
    name = os.path.splitext(os.path.basename(path))[0]
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return []

    out: list[tuple[str, str]] = []

    def walk(key: str, val) -> None:
        if isinstance(val, dict):
            scalars: dict = {}
            for k, v in val.items():
                if isinstance(v, dict) or (
                    isinstance(v, list) and v and isinstance(v[0], dict)
                ):
                    walk(f"{key} > {k}", v)
                else:
                    scalars[k] = v
            if scalars:
                out.append((f"{name} > {key}", "\n".join(_scalar_lines(scalars))))
        elif isinstance(val, list):
            for item in val:
                if isinstance(item, dict):
                    label = (item.get("name") or item.get("id")
                             or item.get("verdict") or item.get("mode")
                             or item.get("case") or item.get("title") or "item")
                    walk(f"{key} > {label}", item)
                else:
                    out.append((f"{name} > {key}", f"{key}: {item}"))
        else:
            out.append((f"{name} > {key}", f"{key}: {val}"))

    for k, v in data.items():
        walk(k, v)

    return [(h, b) for h, b in out if len(b) >= MIN_CHUNK_CHARS]


def _tf(terms: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for t in terms:
        out[t] = out.get(t, 0) + 1
    return out


def build(course_dir: str, out_path: str, knowledge_dir: str | None = None) -> dict:
    """Walk course_dir, chunk, index, write JSON. Deterministic given input.

    If knowledge_dir is given, operational JSON files are flattened into
    headed sections and indexed alongside the prose. They are not copied --
    the JSON stays the single source of truth.
    """
    chunks: list[dict] = []
    df: dict[str, int] = {}
    tdf: dict[str, int] = {}

    docs: list[tuple[str, list[tuple[str, str]]]] = []

    for root, _dirs, files in os.walk(course_dir):
        for fn in sorted(files):
            if not fn.lower().endswith(".md"):
                continue
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, course_dir)
            try:
                with open(full, "r", encoding="utf-8", errors="replace") as f:
                    text = f.read()
            except OSError:
                continue
            docs.append((rel, _split_sections(text)))

    if knowledge_dir and os.path.isdir(knowledge_dir):
        for fn in sorted(os.listdir(knowledge_dir)):
            if not fn.endswith(".json") or fn == "pack.json":
                continue
            try:
                docs.append((f"knowledge/{fn}",
                             _json_sections(os.path.join(knowledge_dir, fn))))
            except (OSError, ValueError):
                continue

    for rel, sections in docs:
        for heading, body in sections:
            title_terms = _tokens(heading)
            ttf = _tf(title_terms)
            for piece in _subchunk(body):
                # Lesson 1: every sub-chunk carries its heading.
                piece = f"{heading}\n{piece}" if heading != "(preamble)" else piece
                terms = _tokens(piece)
                if not terms:
                    continue
                tf = _tf(terms)
                for t in tf:
                    df[t] = df.get(t, 0) + 1
                for t in ttf:
                    tdf[t] = tdf.get(t, 0) + 1
                chunks.append({
                    "id": len(chunks),
                    "src": rel,
                    "title": heading,
                    "text": piece,
                    "len": len(terms),
                    "tf": tf,
                    "tlen": len(title_terms),
                    "ttf": ttf,
                })

    if not chunks:
        raise SystemExit(f"no chunks found under {course_dir}")

    index = {
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "version": 2,
        "course_dir": os.path.abspath(course_dir),
        "k1": K1,
        "b": B,
        "title_weight": TITLE_WEIGHT,
        "n_chunks": len(chunks),
        "avgdl": sum(c["len"] for c in chunks) / len(chunks),
        "avgtl": sum(c["tlen"] for c in chunks) / len(chunks) or 1.0,
        "df": df,
        "tdf": tdf,
        "chunks": chunks,
    }
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False)
    os.replace(tmp, out_path)  # atomic -- never leave a half-written index
    return index


def load(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _bm25(q_terms, tf, dl, df, n, avgdl, k1, b) -> float:
    s = 0.0
    for t in q_terms:
        f = tf.get(t)
        if not f:
            continue
        d = df.get(t, 0)
        idf = math.log(1 + (n - d + 0.5) / (d + 0.5))
        s += idf * (f * (k1 + 1)) / (f + k1 * (1 - b + b * dl / avgdl))
    return s


def query(index: dict, question: str, k: int = 4) -> list[dict]:
    """BM25 body + weighted BM25 heading. Returns top-k chunks verbatim."""
    q_terms = _tokens(question)
    if not q_terms:
        return []
    n = index["n_chunks"]
    avgdl = index["avgdl"]
    avgtl = index.get("avgtl") or 1.0
    df = index["df"]
    tdf = index.get("tdf") or {}
    k1, b = index["k1"], index["b"]
    tw = index.get("title_weight", TITLE_WEIGHT)

    scored: list[tuple[float, dict]] = []
    for c in index["chunks"]:
        s = _bm25(q_terms, c["tf"], c["len"], df, n, avgdl, k1, b)
        if c.get("ttf"):
            s += tw * _bm25(q_terms, c["ttf"], c.get("tlen", 1), tdf, n,
                            avgtl, k1, b)
        if s > 0:
            scored.append((s, c))
    scored.sort(key=lambda x: (-x[0], x[1]["id"]))
    return [
        {"score": round(s, 4), "src": c["src"], "title": c["title"], "text": c["text"]}
        for s, c in scored[:k]
    ]
