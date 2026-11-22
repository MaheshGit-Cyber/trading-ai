"""KCS Sovereign-R1 — 5-Tier Parallel Institutional Multi-Agent Council
Founder & Lead Architect: Kandakatla Mahesh
Firm: Kandakatla Capital Systems (KCS)

This module implements a 5-tier institutional council where 4 specialized
AI agents run IN PARALLEL via ThreadPoolExecutor (<4s latency), followed by
the Supreme Chief Decision Maker (NVIDIA 550B Ultra) who enforces the 3/5
majority vote and non-negotiable Risk Veto:

Tier 1: Agent 1 (Math & Greeks Specialist) -> NVIDIA 30B Reasoning Engine
Tier 2: Agent 2 (Technical Momentum Specialist) -> Groq 120B Engine
Tier 3: Agent 3 (Devil's Advocate Risk Hunter) -> Google Gemini 3.5 Flash-Lite
Tier 4: Agent 4 (Macro & Regime Alignment) -> Moonshot Kimi K3.1 Pro / Gemma
Tier 5: Supreme Chief Officer -> NVIDIA 550B Nemotron-3 Ultra (Final Binding Verdict)
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import sys
import time
from typing import Any, Dict

sys.path.insert(0, "/storage/emulated/0/Trading_AI/trading-ai")
from adapters.base import get_adapter
from brain.master_brain import get_master_brain
from engine.market_grounding_hub import get_grounding_hub

CONFIG_PATH = "/storage/emulated/0/Trading_AI/trading-ai/config/models.json"


class MultiAgentCouncil:
    """5-Tier Parallel Institutional Decision Council for KCS Sovereign-R1."""

    def __init__(self, config_path: str = CONFIG_PATH):
        self.config_path = config_path
        with open(self.config_path, "r", encoding="utf-8") as f:
            self.cfg = json.load(f)

        self.master_brain = get_master_brain()
        self.grounding_hub = get_grounding_hub()

        # Initialize the 5 specialized adapters
        self.chief_adapter = get_adapter(self.cfg, "nvidia_550b_chief")       # 550B Chief
        self.math_adapter = get_adapter(self.cfg, "nvidia_30b_math")          # 30B Math & Greeks
        self.tech_adapter = get_adapter(self.cfg, "groq_120b_tech")           # 120B Momentum
        self.devils_adapter = get_adapter(self.cfg, "gemini_devils_advocate") # Gemini Devil
        self.macro_adapter = get_adapter(self.cfg, "nvidia_macro_lightning")  # 30B Lightning Macro (0.7s)

    def _run_math_agent(self, market_state: Dict[str, Any]) -> str:
        system = (
            "You are Agent 1 (Quantitative Mathematics & Options Greeks Specialist) of KCS Sovereign-R1, "
            "engineered by Kandakatla Mahesh for Kandakatla Capital Systems (KCS). "
            "Evaluate volatility (ATR), expected payoff, position sizing for 1% portfolio risk, "
            "and calculate net expected return after 0.05% slippage/fees."
        )
        user = f"Market State for {market_state.get('symbol')}:\n{json.dumps(market_state, indent=2)}"
        return self.math_adapter.complete(system, user, max_tokens=400)

    def _run_tech_agent(self, market_state: Dict[str, Any]) -> str:
        system = (
            "You are Agent 2 (Technical Momentum & Execution Specialist) of KCS Sovereign-R1, "
            "engineered by Kandakatla Mahesh for Kandakatla Capital Systems (KCS). "
            "Evaluate price vs 20-DMA / 200-DMA, RSI-14, volume divergence, and support/resistance zones. "
            "Propose strict Entry Zone, Stop-Loss, Target 1, Target 2, and R:R ratio."
        )
        user = f"Market State for {market_state.get('symbol')}:\n{json.dumps(market_state, indent=2)}"
        return self.tech_adapter.complete(system, user, max_tokens=400)

    def _run_devils_agent(self, market_state: Dict[str, Any]) -> str:
        system = (
            "You are Agent 3 (Devil's Advocate & Risk Invalidation Hunter) of KCS Sovereign-R1, "
            "engineered by Kandakatla Mahesh for Kandakatla Capital Systems (KCS). "
            "Your sole objective is to aggressively challenge the market state. "
            "Identify liquidity traps, false breakouts, impending macro shocks, and funding squeezes. "
            "State your Risk Score (1-10) and whether to PROCEED, TIGHTEN_STOP, or VETO_TO_CASH_SHIELD."
        )
        user = f"Market State for {market_state.get('symbol')}:\n{json.dumps(market_state, indent=2)}"
        return self.devils_adapter.complete(system, user, max_tokens=400)

    def _run_macro_agent(self, market_state: Dict[str, Any]) -> str:
        system = (
            "You are Agent 4 (Macro Context & Multi-Timeframe Alignment Specialist) of KCS Sovereign-R1, "
            "engineered by Kandakatla Mahesh for Kandakatla Capital Systems (KCS). "
            "Evaluate higher timeframe structural bias (Daily / 4h), broader market correlation (BTC dominance / DXY), "
            "and determine if current market regime is Trending Bullish, Trending Bearish, or Choppy Range."
        )
        user = f"Market State for {market_state.get('symbol')}:\n{json.dumps(market_state, indent=2)}"
        return self.macro_adapter.complete(system, user, max_tokens=400)

    def convene_council(self, asset_class: str = "crypto_assets", market_state: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """Execute parallel deliberation across the 4 specialist agents, grounded with live chart & news tools."""
        t_start = time.time()
        symbol = (market_state or {}).get("symbol", "BTC/USDT")
        
        # Ground with Real-Time Chart Telemetry, Live News, and 16-Year Database
        if not market_state or "verified_truth_anchors" not in market_state:
            market_state = self.grounding_hub.get_grounded_market_intelligence(symbol)

        live_price = market_state.get("verified_truth_anchors", {}).get("live_price_usd", 0.0)

        # -------------------------------------------------------------
        # Phase 1: PARALLEL EXECUTION OF THE 4 SPECIALIST AGENTS
        # -------------------------------------------------------------
        t_parallel_start = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            future_math = executor.submit(self._run_math_agent, market_state)
            future_tech = executor.submit(self._run_tech_agent, market_state)
            future_devils = executor.submit(self._run_devils_agent, market_state)
            future_macro = executor.submit(self._run_macro_agent, market_state)

            math_rep = future_math.result()
            tech_rep = future_tech.result()
            devils_rep = future_devils.result()
            macro_rep = future_macro.result()
        t_parallel = time.time() - t_parallel_start

        # -------------------------------------------------------------
        # Phase 2: SUPREME CHIEF DECISION MAKER (NVIDIA 550B NEMOTRON ULTRA)
        # -------------------------------------------------------------
        chief_system = self.master_brain.generate_cortex_system_prompt(asset_class)
        chief_user = (
            f"COUNCIL OF 5 INSTITUTIONAL DELIBERATION FOR {symbol} (Live Price: ${live_price:,.2f}):\n\n"
            f"=== [AGENT 1: 30B QUANTITATIVE MATH & PAYOFF] ===\n{math_rep}\n\n"
            f"=== [AGENT 2: 120B TECHNICAL MOMENTUM & LEVELS] ===\n{tech_rep}\n\n"
            f"=== [AGENT 3: DEVIL'S ADVOCATE RISK HUNTER] ===\n{devils_rep}\n\n"
            f"=== [AGENT 4: MACRO & MULTI-TIMEFRAME REGIME] ===\n{macro_rep}\n\n"
            f"=== [SUPREME EXECUTIVE MANDATE] ===\n"
            f"You are the Supreme Chief Decision Maker of KCS Sovereign-R1 under Founder Kandakatla Mahesh.\n"
            f"Apply the Weighted Consensus Protocol (Supermajority 3/5 Rule + Risk Veto):\n"
            f"1. Council Vote Tally (How many agents approve vs reject)\n"
            f"2. Final Council Decision (APPROVED_FOR_EXECUTION / REJECTED_TO_CASH_SHIELD)\n"
            f"3. Strict Execution Parameters (Entry Zone, Stop-Loss, Target 1, Target 2, Net R:R)\n"
            f"4. Exact Position Size & Capital Allocation (% of Equity, max 1.0% risk)\n"
            f"5. Devil's Advocate Failure Condition (Exact point that invalidates the trade)"
        )
        t_chief_start = time.time()
        chief_verdict = self.chief_adapter.complete(chief_system, chief_user, max_tokens=800)
        t_chief = time.time() - t_chief_start

        t_total = time.time() - t_start

        return {
            "symbol": symbol,
            "live_price": live_price,
            "total_latency_seconds": round(t_total, 2),
            "parallel_phase_seconds": round(t_parallel, 2),
            "chief_phase_seconds": round(t_chief, 2),
            "agent_1_math_30b": math_rep,
            "agent_2_tech_120b": tech_rep,
            "agent_3_devils_advocate": devils_rep,
            "agent_4_macro_regime": macro_rep,
            "agent_5_supreme_chief_550b": chief_verdict
        }


def get_council() -> MultiAgentCouncil:
    return MultiAgentCouncil()


if __name__ == "__main__":
    council = get_council()
    print("[+] KCS Sovereign-R1 5-Tier Parallel Council Initialized!")
    print(f"[+] Chief: {council.cfg['council']['chief_officer']} (550B)")
    print(f"[+] Math: {council.cfg['council']['math_specialist']} (30B)")
    print(f"[+] Tech: {council.cfg['council']['technical_execution']} (120B)")
    print(f"[+] Devil: {council.cfg['council']['devils_advocate']} (Gemini 3.5 Flash)")
    print(f"[+] Macro: {council.cfg['council']['macro_context']} (Kimi Macro)")
