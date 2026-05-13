from __future__ import annotations

from dataclasses import dataclass
import time

from reliability_lab.cache import ResponseCache, SharedRedisCache
from reliability_lab.circuit_breaker import CircuitBreaker, CircuitOpenError
from reliability_lab.providers import FakeLLMProvider, ProviderError, ProviderResponse


@dataclass(slots=True)
class GatewayResponse:
    text: str
    route: str
    route_reason: str
    provider: str | None
    cache_hit: bool
    latency_ms: float
    estimated_cost: float
    error: str | None = None


class ReliabilityGateway:
    """Routes requests through cache, circuit breakers, and fallback providers."""

    def __init__(
        self,
        providers: list[FakeLLMProvider],
        breakers: dict[str, CircuitBreaker],
        cache: ResponseCache | SharedRedisCache | None = None,
        max_total_cost: float | None = None,
    ):
        self.providers = providers
        self.breakers = breakers
        self.cache = cache
        self.max_total_cost = max_total_cost
        self.cumulative_cost = 0.0

    def _cheapest_provider_cost(self) -> float:
        return min(provider.cost_per_1k_tokens for provider in self.providers)

    def _skip_due_to_budget(self, provider: FakeLLMProvider) -> bool:
        if self.max_total_cost is None or self.cumulative_cost <= self.max_total_cost:
            return False
        cheapest = self._cheapest_provider_cost()
        return provider.cost_per_1k_tokens > cheapest

    def complete(self, prompt: str) -> GatewayResponse:
        """Return a reliable response or a static fallback.

        TODO(student): Improve route reasons, cache safety checks, and error handling.
        TODO(student): Add cost budget check — if cumulative cost exceeds a threshold,
        skip expensive providers and route to cache or cheaper fallback.
        """
        start = time.perf_counter()
        if self.cache is not None:
            cached, score = self.cache.get(prompt)
            if cached is not None:
                latency_ms = (time.perf_counter() - start) * 1000
                return GatewayResponse(
                    text=cached,
                    route="primary",
                    route_reason=f"cache_hit:score={score:.2f}",
                    provider=None,
                    cache_hit=True,
                    latency_ms=latency_ms,
                    estimated_cost=0.0,
                )

        last_error: str | None = None
        error_chain: list[str] = []
        fallback_reason = "none"
        for provider in self.providers:
            if self._skip_due_to_budget(provider):
                fallback_reason = f"{provider.name}:budget_skip"
                error_chain.append(fallback_reason)
                continue
            breaker = self.breakers[provider.name]
            try:
                response: ProviderResponse = breaker.call(provider.complete, prompt)
                if self.cache is not None:
                    self.cache.set(prompt, response.text, {"provider": provider.name})
                route = "primary" if provider == self.providers[0] else "fallback"
                route_reason = f"{route}:{provider.name}"
                if route == "fallback":
                    route_reason = f"fallback:{provider.name}|reason={fallback_reason}"
                latency_ms = (time.perf_counter() - start) * 1000
                self.cumulative_cost += response.estimated_cost
                return GatewayResponse(
                    text=response.text,
                    route=route,
                    route_reason=route_reason,
                    provider=provider.name,
                    cache_hit=False,
                    latency_ms=latency_ms,
                    estimated_cost=response.estimated_cost,
                )
            except (ProviderError, CircuitOpenError) as exc:
                last_error = str(exc)
                reason = "circuit_open" if isinstance(exc, CircuitOpenError) else "provider_error"
                fallback_reason = f"{provider.name}:{reason}"
                error_chain.append(fallback_reason)
                continue

        latency_ms = (time.perf_counter() - start) * 1000
        if error_chain:
            last_error = "; ".join(error_chain)
        return GatewayResponse(
            text="The service is temporarily degraded. Please try again soon.",
            route="static_fallback",
            route_reason="static_fallback:all_providers_failed",
            provider=None,
            cache_hit=False,
            latency_ms=latency_ms,
            estimated_cost=0.0,
            error=last_error,
        )
