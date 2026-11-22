"""KCS Sovereign-R1 — Multi-Agent Institutional Council Engine
Founder & Lead Architect: Kandakatla Mahesh
Firm: Kandakatla Capital Systems (KCS)

This module orchestrates a 3-tier ensemble of specialized AI models to evaluate
market opportunities collaboratively with zero single-model bias:
- Agent 1 (Execution & Momentum): Groq 120B Flagship Model
- Agent 2 (Devil's Advocate & Invalidation): Google Gemini 3.5 Flash-Lite
- Agent 3 (Supreme Chief Decision Maker): NVIDIA 550B Nemotron-3 Ultra
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict

sys.path.insert(0, "/storage/emulated/0/Trading_AI/trading-ai")
from adapters.base import get_adapter
from brain.master_brain import get_master_brain

CONFIG_PATH = "/storage/emulated/0/Trading_AI/trading-ai/config/models.json"


class MultiAgentCouncil:
    """Multi-Agent Institutional Decision Council for KCS Sovereign-R1."""

    def __init__(self, config_path: str = CONFIG_PATH):
        self.config_path = config_path
        with open(self.config_path, "r", encoding="utf-8") as f:
            self.cfg = json.load(f)

        self.master_brain = get_master_brain()
        
        # Initialize specialized adapters
        self.chief_adapter = get_adapter(self.cfg, "nvidia_nim")       # 550B
        self.tech_adapter = get_adapter(self.cfg, "groq_cloud")         # 120B
        self.devils_adapter = get_adapter(self.cfg, "google_gemini")    # Gemini 3.5 Flash

    def convene_council(self, asset_class: str, market_state: Dict[str, Any]) -> Dict[str, Any]:
        """Convene the Council of AI models to deliberate on live market data."""
        t_start = time.time()
        symbol = market_state.get("symbol", "UNKNOWN")
        live_price = market_state.get("live_price_usd", 0.0)

        # -------------------------------------------------------------
        # Phase 1: Technical & Momentum Execution Agent (Groq 120B)
        # -------------------------------------------------------------
        tech_system = (
            "You are Agent 1 (Technical & Momentum Execution Specialist) of KCS Sovereign-R1, "
            "engineered by Kandakatla Mahesh for Kandakatla Capital Systems. "
            "Your job is to analyze price action, moving averages, RSI, ATR, and generate an exact "
            "technical setup with Entry, Stop-Loss, Target 1, Target 2, and R:R ratio."
        )
        tech_user = (
            f"Analyze technical setup for {symbol}:\n"
            f"{json.dumps(market_state, indent=2)}\n"
            f"Provide: Proposed Direction (LONG/SHORT/NEUTRAL), Entry Zone, Stop-Loss, Target 1, Target 2, R:R."
        )
        t0 = time.time()
        tech_assessment = self.tech_adapter.complete(tech_system, tech_user)
        t_tech = time.time() - t0

        # -------------------------------------------------------------
        # Phase 2: Devil's Advocate & Risk Invalidation (Gemini 3.5 Flash)
        # -------------------------------------------------------------
        devils_system = (
            "You are Agent 2 (Devil's Advocate & Risk Invalidation Hunter) of KCS Sovereign-R1, "
            "engineered by Kandakatla Mahesh for Kandakatla Capital Systems. "
            "Your sole objective is to aggressively challenge the proposed technical trade. "
            "Search for liquidity traps, false breakouts, macro headwinds, and structural failure modes. "
            "Give a Risk Rating (1-10) and state whether to PROCEED, TIGHTEN_STOP, or VETO (CASH_SHIELD)."
        )
        devils_user = (
            f"Review this market state and Agent 1's proposed setup for {symbol}:\n\n"
            f"MARKET STATE:\n{json.dumps(market_state, indent=2)}\n\n"
            f"AGENT 1 (120B TECH) PROPOSAL:\n{tech_assessment}\n\n"
            f"Hunt for weaknesses and output your Devil's Advocate critique and Veto/Proceed recommendation."
        )
        t0 = time.time()
        devils_critique = self.devils_adapter.complete(devils_system, devils_user)
        t_devils = time.time() - t0

        # -------------------------------------------------------------
        # Phase 3: Supreme Chief Decision Maker (NVIDIA 550B Nemotron-3 Ultra)
        # -------------------------------------------------------------
        chief_system = self.master_brain.generate_cortex_system_prompt(asset_class)
        chief_user = (
            f"COUNCIL DELIBERATION FOR {symbol} (Live Price: ${live_price:,.2f}):\n\n"
            f"--- [AGENT 1: 120B TECHNICAL EXECUTION] ---\n"
            f"{tech_assessment}\n\n"
            f"--- [AGENT 2: DEVIL'S ADVOCATE CRITIQUE] ---\n"
            f"{devils_critique}\n\n"
            f"--- [SUPREME MANDATE] ---\n"
            f"As Supreme Chief of KCS Sovereign-R1 under Kandakatla Mahesh:\n"
            f"Synthesize both agents' arguments against Master Brain Directives.\n"
            f"Emit the FINAL INSTITUTIONAL VERDICT:\n"
            f"1. Final Council Decision (APPROVED / REJECTED_TO_CASH_SHIELD)\n"
            f"2. Strict Final Execution Order (Entry, Final SL, Final Targets, Net R:R)\n"
            f"3. Capital Allocation (% of Equity)\n"
            f"4. Council Consensus Summary"
        )
        t0 = time.time()
        chief_verdict = self.chief_adapter.complete(chief_system, chief_user)
        t_chief = time.time() - t0

        t_total = time.time() - t_start

        return {
            "symbol": symbol,
            "live_price": live_price,
            "total_latency_seconds": round(t_total, 2),
            "council_latencies": {
                "agent_1_groq_120b": round(t_tech, 2),
                "agent_2_gemini_35": round(t_devils, 2),
                "agent_3_nvidia_550b": round(t_chief, 2)
            },
            "agent_1_technical_120b": tech_assessment,
            "agent_2_devils_advocate": devils_critique,
            "agent_3_supreme_verdict_550b": chief_verdict
        }


def get_council() -> MultiAgentCouncil:
    return MultiAgentCouncil()


if __name__ == "__main__":
    council = get_council()
    print("[+] KCS Sovereign-R1 Multi-Agent Council Initialized!")
    print(f"[+] Chief: {council.cfg['council']['chief_officer']} (550B)")
    print(f"[+] Tech: {council.cfg['council']['technical_execution']} (120B)")
    print(f"[+] Devil: {council.cfg['council']['devils_advocate']} (Gemini 3.5 Flash)")
