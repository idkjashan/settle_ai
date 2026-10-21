"""In-memory state-machine circuit breaker and exponential jitter retry policies."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any, Awaitable, Callable, TypeVar

from app.domain.vlm_damage_inspection.exceptions import Stage3CircuitBreakerOpenError

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitBreaker:
    """State-machine circuit breaker (CLOSED -> OPEN -> HALF_OPEN).

    Prevents cascading resource exhaustion and network thundering herd against
    failing or saturated VLM endpoints.
    """

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state: str = "CLOSED"  # "CLOSED", "OPEN", "HALF_OPEN"
        self.failure_count: int = 0
        self.last_state_change: float = time.time()

    def record_success(self) -> None:
        """Record successful execution; reset failure counter and close circuit."""
        if self.state in ("HALF_OPEN", "OPEN"):
            logger.info("Circuit breaker recovered to CLOSED state.")
        self.state = "CLOSED"
        self.failure_count = 0
        self.last_state_change = time.time()

    def record_failure(self) -> None:
        """Record an execution failure and trip circuit to OPEN if threshold exceeded."""
        self.failure_count += 1
        logger.warning(
            "Circuit breaker recorded failure %d/%d (state: %s)",
            self.failure_count,
            self.failure_threshold,
            self.state,
        )
        if self.state == "HALF_OPEN" or self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            self.last_state_change = time.time()
            logger.error(
                "Circuit breaker tripped to OPEN state (threshold %d reached). Cooling for %.1fs.",
                self.failure_threshold,
                self.recovery_timeout,
            )

    def reset(self) -> None:
        """Manually reset the circuit breaker to CLOSED state."""
        self.state = "CLOSED"
        self.failure_count = 0
        self.last_state_change = time.time()

    async def call(self, func: Callable[[], Awaitable[T]]) -> T:
        """Execute async function guarded by circuit state."""
        now = time.time()

        if self.state == "OPEN":
            if now - self.last_state_change > self.recovery_timeout:
                logger.info("Recovery timeout elapsed. Circuit transitioning to HALF_OPEN probe state.")
                self.state = "HALF_OPEN"
                self.last_state_change = now
            else:
                remaining = self.recovery_timeout - (now - self.last_state_change)
                raise Stage3CircuitBreakerOpenError(
                    f"VLM Provider Circuit Breaker is OPEN. Cooling for {remaining:.1f}s remaining."
                )

        try:
            result = await func()
            self.record_success()
            return result
        except Exception:
            self.record_failure()
            raise


async def execute_with_jitter_retry(
    func: Callable[[], Awaitable[T]],
    max_retries: int = 2,
    base_delays: tuple[float, ...] = (0.5, 1.0, 2.0),
) -> T:
    """Execute an async callable with exponential backoff and randomized jitter."""
    last_exc: Optional[Exception] = None
    total_attempts = max_retries + 1

    for attempt in range(total_attempts):
        try:
            return await func()
        except Exception as exc:
            last_exc = exc
            if attempt == total_attempts - 1:
                break

            delay_idx = min(attempt, len(base_delays) - 1)
            sleep_time = base_delays[delay_idx] + random.uniform(0.05, 0.25)
            logger.warning(
                "Attempt %d/%d failed with %s: retrying in %.2fs",
                attempt + 1,
                total_attempts,
                type(exc).__name__,
                sleep_time,
            )
            await asyncio.sleep(sleep_time)

    assert last_exc is not None
    raise last_exc
