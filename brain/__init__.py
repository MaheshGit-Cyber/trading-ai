"""Deterministic trading-AI brain core.

This package is deliberately split into:

- ``contracts``: typed, JSON-serialisable outputs. No I/O, no model calls.
- ``data``: point-in-time readers for the local NSE/crypto files.
- ``scorer``: pure scoring functions. No network, no LLM, no look-ahead.

The LLM layer must only format these precomputed facts; it may not invent
numbers or override the deterministic score.
"""

__version__ = "0.1.0"
