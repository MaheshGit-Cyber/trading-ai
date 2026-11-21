"""Research-only agent powers for the trading system.

This package is deliberately separate from ``brain`` (deterministic scores)
and ``engine`` (evidence/RAG). It adds:

- ``clock``: live IST time/date and market-session context
- ``news_guard``: credibility/fake-news risk assessment (not a truth oracle)
- ``web_research``: safe URL fetch, web search and news RSS
- ``memory``: append-only research memory
- ``strategy_lab``: pre-registered hypotheses and frozen promotion gates

It has no broker, order, real-money or self-promotion permission.
"""

__version__ = "0.1.0"
