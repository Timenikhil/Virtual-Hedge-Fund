"""Stub local AI allocator for load testing.

Set via env vars:
    AI_ALLOCATOR_MODE=local
    AI_ALLOCATOR_LOCAL_MODULE=tests.load.fake_allocator

Optional env:
    FAKE_ALLOCATOR_SLEEP_MS  — sleep before returning (simulates slow LLM)
    FAKE_ALLOCATOR_FAIL_RATE — float 0..1, raise on a fraction of calls
"""

from __future__ import annotations

import os
import random
import time
from typing import Any


def allocate_weights(context: dict[str, Any]) -> list[float]:
    sleep_ms = float(os.getenv("FAKE_ALLOCATOR_SLEEP_MS", "0"))
    if sleep_ms > 0:
        time.sleep(sleep_ms / 1000.0)

    fail_rate = float(os.getenv("FAKE_ALLOCATOR_FAIL_RATE", "0"))
    if fail_rate > 0 and random.random() < fail_rate:
        raise RuntimeError("fake_allocator: simulated provider failure")

    strategies = context.get("strategies") or []
    n = len(strategies)
    if n == 0:
        raise ValueError("fake_allocator: empty strategies list in context")
    return [1.0 / n] * n
