"""Shared utilities for ``perfrace.collect`` pipelines.

Modules under ``perfrace.collect.utils`` are general-purpose helpers
used by more than one collector.

The most prominent member is :mod:`~perfrace.collect.utils.tokens`,
which provides a thread-safe, rate-limit-aware GitHub credential pool.
"""

from .tokens import Token, TokenPool, load_tokens

__all__ = ["Token", "TokenPool", "load_tokens"]
