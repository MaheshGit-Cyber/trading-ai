"""Model adapters. ONE interface, three transports.

The whole point: engine code never knows which provider is active.
Swap `active` in config/models.json and nothing else changes.

Memory (memory/) and the deterministic gate (engine/) live OUTSIDE
this package on purpose -- they must survive a provider swap.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Protocol


class ModelAdapter(Protocol):
    def complete(self, system: str, user: str) -> str:
        """Return the raw model reply as text. Raise on transport failure."""
        ...


class OpenAICompat:
    """Works for: local llama.cpp/Ollama, the OpenCode HTTP gateway, paid APIs.

    All three speak the same wire format, which is why the swap is config-only.
    """

    def __init__(self, cfg: dict):
        self.base_url = (cfg.get("base_url") or "").rstrip("/")
        self.model = cfg.get("model") or ""
        self.auth = cfg.get("auth") or "none"
        self.timeout = int(cfg.get("timeout_s") or 60)
        if not self.base_url:
            raise ValueError("provider.base_url is empty -- fill it in config/models.json")

    def _headers(self) -> dict:
        h = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        if self.auth == "bearer_public":
            h["Authorization"] = "Bearer public"
        elif self.auth.startswith("bearer:"):
            h["Authorization"] = f"Bearer {self.auth[7:]}"
        elif self.auth.startswith("env:"):
            env_name = self.auth[4:]
            key = os.environ.get(env_name, "")
            if not key:
                # Try loading from local .env file
                env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
                if os.path.exists(env_path):
                    with open(env_path, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith(f"{env_name}="):
                                key = line.split("=", 1)[1].strip().strip('"').strip("'")
                                os.environ[env_name] = key
                                break
            if not key:
                raise RuntimeError(f"env var {env_name} is not set")
            h["Authorization"] = f"Bearer {key}"
        elif self.auth == "none":
            pass
        else:
            raise ValueError(f"unknown auth mode: {self.auth}")
        return h

    def complete(self, system: str, user: str) -> str:
        body = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body, method="POST", headers=self._headers(),
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8")[:300]
            except Exception:
                pass
            raise RuntimeError(f"HTTP {e.code} from {self.base_url}: {detail}") from e
        except Exception as e:
            raise RuntimeError(f"transport failed for {self.base_url}: {e}") from e

        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"unexpected response shape: {json.dumps(data)[:300]}") from e


class OpenCodeCLI:
    """Shells out to `opencode run --format json`.

    This is the path that actually works right now. Direct HTTP to the same
    gateway returns 429 FreeUsageLimitError; the CLI succeeds.

    CRITICAL: `opencode run` is an AGENT, not a completion endpoint. If it
    starts in a directory containing AGENTS.md and .opencode/skills, it loads
    them, may enter tool loops, and burns the free quota -- observed as 90s
    timeouts and then FreeUsageLimitError. Running from a clean directory with
    no AGENTS.md and no skills turns it back into a plain one-shot call
    (measured: 8-question prompt, 17s, no tool calls).

    `--standalone` is also required. The shared background service owns
    configuration for its project, so it ignores the clean cwd's
    `opencode.json` and reports `Agent not found: "plain"`. A private server
    loads the clean config.

    `PWD` must be set to the clean cwd as well. `subprocess(cwd=...)` calls
    chdir but does not update the inherited `PWD` env var, and OpenCode uses
    `PWD` for project/config discovery. Without this the child still sees the
    caller's project and reports `Agent not found: "plain"`.
    """

    def __init__(self, cfg: dict):
        import tempfile

        self.model = cfg.get("model") or ""
        self.timeout = int(cfg.get("timeout_s") or 180)
        self.agent = cfg.get("agent") or "plain"
        # Clean cwd is not cosmetic -- it is what prevents skill/tool loading.
        self.cwd = cfg.get("cwd") or os.path.join(
            tempfile.gettempdir(), "opencode-ai-clean")
        os.makedirs(self.cwd, exist_ok=True)
        self._ensure_plain_agent()
        if not self.model:
            raise ValueError("provider.model is empty for opencode_cli")

    def _ensure_plain_agent(self) -> None:
        """Materialise a tool-less agent config in the clean cwd.

        Without this, `opencode run` keeps its tool belt even in an empty
        directory: it runs shell commands, reads files, and each step is a
        separate model call. That is what drained the free quota and produced
        90s timeouts followed by FreeUsageLimitError.

        OpenCode V2 uses `agents` (plural) and `permissions` rules. The V1
        shape (`agent` / `tools`) is silently ignored, which surfaces as
        `Agent not found: "plain"`. So this file is rewritten every time
        instead of written once -- a stale V1 file would never self-heal.
        """
        path = os.path.join(self.cwd, "opencode.json")
        cfg = {
            "$schema": "https://opencode.ai/config.json",
            "default_agent": self.agent,
            "agents": {
                self.agent: {
                    "description": "Tool-less single-shot completion.",
                    "mode": "primary",
                    "model": self.model,
                    "steps": 1,
                    "permissions": [
                        {"action": "*", "resource": "*", "effect": "deny"},
                    ],
                }
            },
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)

    def complete(self, system: str, user: str) -> str:
        import subprocess

        # `opencode run` has no separate system channel -- merge them.
        prompt = f"{system.strip()}\n\n---\n\n{user.strip()}"
        cmd = [
            "opencode", "run",
            "--standalone",
            "--format", "json",
            "--agent", self.agent,
            "--model", self.model,
            prompt,
        ]
        try:
            # cwd= chdirs the child but leaves PWD pointing at the caller's
            # project. OpenCode reads PWD for config discovery, so set it.
            env = dict(os.environ, PWD=self.cwd)
            proc = subprocess.run(
                cmd, capture_output=True, text=True, cwd=self.cwd,
                env=env, timeout=self.timeout, errors="replace",
            )
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"opencode run timed out after {self.timeout}s") from e

        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "")[-400:]
            raise RuntimeError(f"opencode run exited {proc.returncode}: {tail}")

        # NDJSON event stream; concatenate the `text` parts in order.
        out: list[str] = []
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("type") == "text":
                part = ev.get("part") or {}
                if isinstance(part.get("text"), str):
                    out.append(part["text"])
        text = "".join(out).strip()
        if not text:
            raise RuntimeError("opencode run produced no text parts")
        return text


def get_adapter(models_config: dict, name: str | None = None) -> ModelAdapter:
    """Resolve the active provider from config/models.json."""
    active = name or models_config.get("active")
    if not active:
        raise ValueError("config has no 'active' provider")
    providers = models_config.get("providers") or {}
    if active not in providers:
        raise ValueError(f"unknown provider '{active}'. Known: {sorted(providers)}")
    cfg = providers[active]
    ptype = cfg.get("type")
    if ptype == "opencode_cli":
        return OpenCodeCLI(cfg)
    if ptype == "openai_compat":
        return OpenAICompat(cfg)
    raise ValueError(f"unknown provider type: {ptype}")
