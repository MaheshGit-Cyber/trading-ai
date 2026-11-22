"""KCS Sovereign-R1 — Master Brain Cortex Engine
Founder & Lead Architect: Kandakatla Mahesh
Firm: Kandakatla Capital Systems (KCS)

This module loads the unified institutional knowledge base from
`kcs_sovereign_master_brain.json` and embeds it directly into the cognitive
cortex of the active model adapter (120B Cloud / Local GGUF).
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict

BRAIN_PATH = "/storage/emulated/0/Trading_AI/trading-ai/brain/kcs_sovereign_master_brain.json"
CONFIG_PATH = "/storage/emulated/0/Trading_AI/trading-ai/config/models.json"


class KCSSovereignMasterBrain:
    """Institutional Cognitive Cortex for KCS Sovereign-R1."""

    def __init__(self, brain_path: str = BRAIN_PATH):
        self.brain_path = brain_path
        self.brain_data = self._load_master_brain()
        self.identity = self.brain_data.get("system_identity", {})
        self.directives = self.brain_data.get("core_directives", [])
        self.verticals = self.brain_data.get("multi_asset_verticals", {})
        self.regimes = self.brain_data.get("market_regime_policies", {})
        self.benchmarks = self.brain_data.get("historical_16_year_empirical_benchmarks", {})

    def _load_master_brain(self) -> Dict[str, Any]:
        if not os.path.exists(self.brain_path):
            raise FileNotFoundError(f"Master Brain file not found at {self.brain_path}")
        with open(self.brain_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def generate_cortex_system_prompt(self, asset_class: str = "crypto_assets") -> str:
        """Construct high-density institutional system prompt directly from the Master Brain."""
        vertical_info = self.verticals.get(asset_class, {})
        
        prompt = (
            f"You are {self.identity.get('model_name', 'KCS Sovereign-R1')}, the flagship quantitative trading "
            f"artificial intelligence engineered by {self.identity.get('creator_and_architect', 'Kandakatla Mahesh')} "
            f"for {self.identity.get('institution', 'Kandakatla Capital Systems (KCS)')}.\n\n"
            f"CORE DIRECTIVES:\n"
        )
        for d in self.directives:
            prompt += f"- {d}\n"

        prompt += f"\nACTIVE VERTICAL SPECIFICATION ({asset_class.upper()}):\n"
        prompt += json.dumps(vertical_info, indent=2) + "\n\n"

        prompt += "MARKET REGIME POLICIES & CASH SHIELD:\n"
        for regime_name, policy in self.regimes.items():
            prompt += f"- {regime_name}: {policy.get('action')} (Condition: {policy.get('indicator_state')})\n"

        prompt += (
            f"\n16-YEAR EMPIRICAL BENCHMARK ({self.benchmarks.get('period', '2010-2026')}):\n"
            f"- Win Rate: {self.benchmarks.get('empirical_win_rate_with_cash_shield')}%\n"
            f"- Profit Factor: {self.benchmarks.get('profit_factor')}\n"
            f"- Core Axiom: {self.benchmarks.get('key_learning')}\n\n"
            f"Always reason mathematically (<think> ... </think>), enforce stop-loss and 1:1.5+ R:R, "
            f"and declare Devil's Advocate failure conditions."
        )
        return prompt

    def evaluate_live_market(self, asset_class: str, market_state: Dict[str, Any]) -> str:
        """Evaluate real-time market data through the active model adapter."""
        sys.path.insert(0, "/storage/emulated/0/Trading_AI/trading-ai")
        from adapters.base import get_adapter

        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            models_cfg = json.load(f)

        adapter = get_adapter(models_cfg)
        system_prompt = self.generate_cortex_system_prompt(asset_class)

        user_prompt = (
            f"Live Ingested Market State for {market_state.get('symbol', 'UNKNOWN')}:\n"
            f"{json.dumps(market_state, indent=2)}\n\n"
            f"Synthesize through your KCS Master Brain:\n"
            f"1. Regime Identification & Cash Shield Check\n"
            f"2. Precise Order Parameters (Entry, SL, T1, T2, R:R)\n"
            f"3. Position Sizing & Cost/Slippage Assessment\n"
            f"4. Devil's Advocate Risk Invalidation"
        )

        return adapter.complete(system_prompt, user_prompt)


def get_master_brain() -> KCSSovereignMasterBrain:
    return KCSSovereignMasterBrain()


if __name__ == "__main__":
    brain = get_master_brain()
    print(f"[+] Loaded Master Brain for: {brain.identity.get('model_name')}")
    print(f"[+] Total Verticals: {len(brain.verticals)}")
    print(f"[+] Directives: {len(brain.directives)}")
    print(f"[+] System Prompt Size: {len(brain.generate_cortex_system_prompt())} characters")
