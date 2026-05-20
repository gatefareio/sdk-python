"""SDK-local spend cap manager.

The single defensive layer that prevents a malicious or misconfigured
resource server from coaxing the wallet into signing an authorization
larger than what the consumer wanted. Always check `authorize()`
BEFORE producing any signature.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from typing import Protocol

from .errors import SpendCapError
from .types import SpendCaps


class SpendStorage(Protocol):
    """Persistence interface for daily spend totals. Implementations
    may use in-memory dict (default), SQLite, Redis, or any other
    backing store. The interface intentionally stays trivial.
    """

    def read(self, day_key: str) -> float: ...
    def add(self, day_key: str, delta: float) -> None: ...


class _MemoryStorage:
    """Default in-process storage. Crash = forget; for long-running
    agents that need crash-safety, pass a persistent SpendStorage to
    SpendCapManager."""

    def __init__(self) -> None:
        self._data: dict[str, float] = {}

    def read(self, day_key: str) -> float:
        return self._data.get(day_key, 0.0)

    def add(self, day_key: str, delta: float) -> None:
        self._data[day_key] = self._data.get(day_key, 0.0) + delta


DEFAULT_SPEND_CAPS: SpendCaps = {
    "per_call_usdc": 1.0,
    "per_day_usdc": 10.0,
}


class SpendCapManager:
    """Tracks daily spend and refuses calls that would exceed caps.

    Bucket boundary is UTC midnight — so callers in any timezone get
    a deterministic reset. Records are made AFTER successful settles
    only; failed settles do not count against the cap.
    """

    def __init__(
        self,
        caps: SpendCaps | None = None,
        storage: SpendStorage | None = None,
        now: Callable[[], float] | None = None,
    ) -> None:
        self._per_call = (caps or {}).get("per_call_usdc", DEFAULT_SPEND_CAPS["per_call_usdc"])
        self._per_day = (caps or {}).get("per_day_usdc", DEFAULT_SPEND_CAPS["per_day_usdc"])
        self._storage: SpendStorage = storage or _MemoryStorage()
        self._now = now or time.time

    def _day_key(self) -> str:
        # UTC YYYY-MM-DD bucket.
        return time.strftime("%Y-%m-%d", time.gmtime(self._now()))

    def authorize(self, attempted_usdc: float, per_call_override_usdc: float | None = None) -> None:
        """Validate a call of `attempted_usdc`. Raises SpendCapError
        on refusal. Does NOT charge — call `record()` afterwards."""
        if not math.isfinite(attempted_usdc) or attempted_usdc < 0:
            raise SpendCapError("per_call_cap_exceeded", attempted_usdc, 0.0)

        per_call_cap = per_call_override_usdc if per_call_override_usdc is not None else self._per_call
        if attempted_usdc > per_call_cap:
            raise SpendCapError("per_call_cap_exceeded", attempted_usdc, per_call_cap)

        spent_today = self._storage.read(self._day_key())
        if spent_today + attempted_usdc > self._per_day:
            raise SpendCapError(
                "per_day_cap_exceeded",
                spent_today + attempted_usdc,
                self._per_day,
            )

    def record(self, usdc: float) -> None:
        """Record a confirmed spend. Call only after on-chain settle
        confirmed."""
        if not math.isfinite(usdc) or usdc < 0:
            return
        self._storage.add(self._day_key(), usdc)

    def spent_today_usdc(self) -> float:
        """Total spend within the current UTC day."""
        return self._storage.read(self._day_key())

    def remaining_today_usdc(self) -> float:
        """Headroom under the daily cap. Floors at zero."""
        return max(0.0, self._per_day - self.spent_today_usdc())
