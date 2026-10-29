"""Credit pricing, usage windows, and atomic admission decisions."""

from dataclasses import dataclass
from typing import Iterable, Mapping, Optional


ROLLING_WINDOW_SECONDS = 5 * 60 * 60
CALENDAR_MONTH_WINDOW_SECONDS = 30 * 24 * 60 * 60  # approximate; real month boundaries live in the database tier


@dataclass(frozen=True)
class Limits:
    rolling_credits: Optional[int] = None
    monthly_credits: Optional[int] = None
    requests_per_minute: Optional[int] = None
    max_output_tokens: Optional[int] = None


@dataclass(frozen=True)
class WindowUsage:
    kind: str  # "rolling" | "calendar_month"
    seconds: int
    credits: int


@dataclass(frozen=True)
class AdmissionDecision:
    allowed: bool
    reserved_credits: int
    remaining_by_window: Mapping[str, Optional[int]]
    reasons: tuple


def credit_cost(input_tokens: int, output_tokens: int, input_weight: float = 1.0, output_weight: float = 2.0) -> int:
    """Price a request from authoritative or estimated token counts."""
    return int(round(input_tokens * input_weight + output_tokens * output_weight))


def usage_in_window(settled: Iterable[tuple], now: float, seconds: int) -> int:
    """Sum settled credits used in (now - seconds, now]."""
    start = now - seconds
    return sum(credits for timestamp, credits in settled if start < timestamp <= now)


def evaluate_admission(reserved_credits: int, windows: list, limits: Limits) -> AdmissionDecision:
    """Check every applicable quota window plus the reservation against the plan caps."""
    allowed = True
    reasons = []
    remaining_by_window = {}
    for window in windows:
        limit = limits.rolling_credits if window.kind == "rolling" else limits.monthly_credits
        remaining = None if limit is None else limit - window.credits - reserved_credits
        remaining_by_window[window.kind] = remaining
        if limit is not None and window.credits + reserved_credits > limit:
            allowed = False
            reasons.append(f"{window.kind}_credits_exceeded")
    return AdmissionDecision(
        allowed=allowed,
        reserved_credits=reserved_credits,
        remaining_by_window=remaining_by_window,
        reasons=tuple(reasons),
    )


class QuotaLedger:
    """Process-local MVP ledger of holds and settlements.

    The durable version stores holds in the database with atomic transactions; this
    in-process ledger keeps admission logic testable before that tier lands.
    """

    def __init__(self, now=None):
        self._now = now if now is not None else 1_000
        self._reserved_credits = 0
        self._settled = {"rolling": []}

    @property
    def reserved_credits(self) -> int:
        return self._reserved_credits

    def _windows(self, now) -> list:
        return [
            WindowUsage(kind="rolling", seconds=ROLLING_WINDOW_SECONDS, credits=usage_in_window(self._settled.get("rolling", []), now, ROLLING_WINDOW_SECONDS)),
            WindowUsage(kind="calendar_month", seconds=CALENDAR_MONTH_WINDOW_SECONDS, credits=usage_in_window(self._settled.get("calendar_month", []), now, CALENDAR_MONTH_WINDOW_SECONDS)),
        ]

    def evaluate(self, request_credits: int, limits: Limits, now=None) -> AdmissionDecision:
        effective_now = now if now is not None else self._now
        return evaluate_admission(request_credits, self._windows(effective_now), limits)

    def reserve(self, request_credits: int, limits: Limits, now=None) -> AdmissionDecision:
        effective_now = now if now is not None else self._now
        decision = self.evaluate(request_credits, limits, now=effective_now)
        if decision.allowed:
            self._reserved_credits += request_credits
        return decision

    def settle(self, request_credits: int, now=None) -> int:
        effective_now = now if now is not None else self._now
        self._reserved_credits = max(0, self._reserved_credits - request_credits)
        self._settled.setdefault("rolling", []).append((effective_now, request_credits))
        return request_credits

    def release(self, request_credits: int, now=None):
        effective_now = now if now is not None else self._now
        self._reserved_credits = max(0, self._reserved_credits - request_credits)
        self._settled.setdefault("rolling", []).append((effective_now, -request_credits))
