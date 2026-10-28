"""Capability constrained, online LinUCB model routing (standard library only)."""

from __future__ import annotations

import json
import math
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class ModelSpec:
    id: str
    provider: str
    input_usd_per_million: float
    output_usd_per_million: float
    capability: float
    context_tokens: int = 128_000
    available: bool = True
    latency_ms: int = 0


@dataclass(frozen=True)
class RouteDecision:
    model_id: str
    task_type: str
    base_complexity: float
    effective_complexity: float
    memory_relevance: float
    reason: str
    alternatives: tuple[str, ...]


HARD_TERMS = re.compile(r"\b(prove|formal|multi[- ]hop|architect|distributed|security audit|derive|trade[- ]offs|step[- ]by[- ]step)\b", re.I)
CODE_TERMS = re.compile(r"```|\b(def |class |async |import |function|stack trace|compile|refactor|bug)\b", re.I)
JSON_TERMS = re.compile(r"\b(json|schema|extract|classify|return only|structured output)\b", re.I)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


class SmartRouter:
    """Route among caller supplied models and learn from outcome feedback.

    Persisted state contains only model IDs and small numeric matrices. Model
    pricing and credentials are always supplied by the caller, keeping current
    provider terms and secrets outside the learning file.
    """

    FORMAT = "nexor-linucb-v1"
    DIM = 8

    def __init__(self, models: Iterable[ModelSpec], state_path: str | Path | None = None,
                 *, alpha: float = 0.18, ridge: float = 1.0, cost_weight: float = 0.12,
                 memory_discount: float = 0.25, latency_weight: float = 0.0):
        self.models = tuple(models)
        if not self.models:
            raise ValueError("At least one model is required")
        if len({model.id for model in self.models}) != len(self.models):
            raise ValueError("Model IDs must be unique")
        for model in self.models:
            rates = (model.input_usd_per_million, model.output_usd_per_million)
            if not all(math.isfinite(rate) and rate >= 0 for rate in rates):
                raise ValueError("Model rates must be finite and non-negative")
            if not 0 <= model.capability <= 1 or model.context_tokens <= 0:
                raise ValueError("Model capability must be in [0, 1] and context_tokens must be positive")
        self.state_path = Path(state_path) if state_path else None
        self.alpha, self.ridge = max(0.0, alpha), max(0.001, ridge)
        self.cost_weight, self.memory_discount = max(0.0, cost_weight), _clamp(memory_discount)
        self.latency_weight = max(0.0, latency_weight)
        self.state: dict[str, dict[str, Any]] = {}
        self._load()

    @staticmethod
    def _features(prompt: str, memory_relevance: float, memory_coverage: float) -> tuple[float, ...]:
        words = prompt.split()
        code = bool(CODE_TERMS.search(prompt))
        hard_count = len(HARD_TERMS.findall(prompt))
        structured = bool(JSON_TERMS.search(prompt))
        reasoning = _clamp(hard_count / 3)
        length = _clamp(len(words) / 1200)
        values = (1.0, length, float(code), reasoning, float(len(prompt) > 7000), float(structured),
                 _clamp(memory_relevance), _clamp(memory_coverage))
        return values

    @staticmethod
    def _dot(left: list[float], right: tuple[float, ...] | list[float]) -> float:
        return sum(a * b for a, b in zip(left, right))

    def _arm(self, model_id: str) -> dict[str, Any]:
        arm = self.state.get(model_id)
        if arm is None:
            arm = {"a_inv": [[(1.0 / self.ridge if i == j else 0.0) for j in range(self.DIM)] for i in range(self.DIM)],
                   "b": [0.0] * self.DIM, "observations": 0}
            self.state[model_id] = arm
        return arm

    def route(self, prompt: str, *, memory_relevance: float = 0.0, memory_coverage: float = 0.0,
              context_tokens: int = 0) -> RouteDecision:
        prompt = str(prompt or "")
        features = self._features(prompt, memory_relevance, memory_coverage)
        _, length, code, reasoning, long_context, structured, relevance, coverage = features
        base = _clamp(0.08 + length * 0.28 + code * 0.16 + reasoning * 0.34 + long_context * 0.14 + structured * 0.05)
        # Memory discounts synthesis only when the prompt indicates it uses prior context.
        uses_memory = bool(re.search(r"\b(remember|previous|above|my project|my preference|as discussed|continue)\b", prompt, re.I))
        effective = _clamp(base - (self.memory_discount * relevance * coverage if uses_memory else 0.0))
        deep_required = bool(HARD_TERMS.search(prompt))
        candidates = [model for model in self.models if model.available and model.context_tokens >= max(0, context_tokens)]
        if deep_required:
            candidates = [model for model in candidates if model.capability >= 0.65]
        capable = [model for model in candidates if model.capability >= effective]
        if not capable:
            raise RuntimeError("No available model meets the task capability and context requirements")
        candidates = capable
        if not candidates:
            raise RuntimeError("No available model meets the task capability and context requirements")

        max_cost = max(1e-9, max(m.input_usd_per_million + m.output_usd_per_million for m in candidates))
        max_latency = max((m.latency_ms for m in candidates), default=0)
        scored = []
        for model in candidates:
            arm = self._arm(model.id)
            a_inv, b = arm["a_inv"], arm["b"]
            theta = [sum(a_inv[i][j] * b[j] for j in range(self.DIM)) for i in range(self.DIM)]
            projected = [sum(a_inv[i][j] * features[j] for j in range(self.DIM)) for i in range(self.DIM)]
            uncertainty = math.sqrt(max(0.0, self._dot(list(features), projected)))
            expected = self._dot(theta, features) + self.alpha * uncertainty
            cost = (model.input_usd_per_million + model.output_usd_per_million) / max_cost
            latency = model.latency_ms / max_latency if model.latency_ms > 0 and max_latency > 0 else 0.5
            # A hard task keeps capability ahead of exploration and cost.
            score = (expected - self.cost_weight * cost - self.latency_weight * latency
                     + 0.3 * model.capability * effective)
            scored.append((score, model))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        selected = scored[0][1]
        task_type = "reasoning" if deep_required else "code" if code else "structured" if structured else "long_context" if long_context else "general"
        reason = "capability constrained contextual-bandit score; memory discount applied" if uses_memory and relevance > 0 else "capability constrained contextual-bandit score"
        return RouteDecision(selected.id, task_type, round(base, 4), round(effective, 4), round(relevance, 4), reason,
                             tuple(model.id for _, model in scored[1:]))

    def update(self, model_id: str, prompt: str, reward: float, *, memory_relevance: float = 0.0,
               memory_coverage: float = 0.0) -> None:
        """Update a selected model from bounded reward in [-2, 1]."""
        if not any(model.id == model_id for model in self.models):
            raise ValueError(f"Unknown model: {model_id}")
        reward = max(-2.0, min(1.0, float(reward)))
        # Rescale the requested [-2, 1] feedback convention to a bounded utility.
        target = (reward + 2.0) / 3.0
        x = self._features(prompt, memory_relevance, memory_coverage)
        arm = self._arm(model_id)
        a_inv = arm["a_inv"]
        ax = [sum(a_inv[i][j] * x[j] for j in range(self.DIM)) for i in range(self.DIM)]
        denom = 1.0 + self._dot(list(x), ax)
        arm["a_inv"] = [[a_inv[i][j] - ax[i] * ax[j] / denom for j in range(self.DIM)] for i in range(self.DIM)]
        arm["b"] = [arm["b"][i] + target * x[i] for i in range(self.DIM)]
        arm["observations"] += 1
        self.save()

    @staticmethod
    def reward_from_signals(*, accepted: bool = False, regenerated: bool = False,
                            correction: bool = False, fallback: bool = False,
                            under_budget: bool = False) -> float:
        if regenerated or correction:
            return -2.0
        if fallback:
            return -1.0
        if accepted or under_budget:
            return 1.0
        return 0.0

    def _load(self) -> None:
        if not self.state_path or not self.state_path.exists():
            return
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        if payload.get("format") == self.FORMAT and isinstance(payload.get("models"), dict):
            known = {model.id for model in self.models}
            self.state = {key: value for key, value in payload["models"].items() if key in known}

    def save(self) -> None:
        if not self.state_path:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temp_name = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.state_path.parent, delete=False) as handle:
                temp_name = handle.name
                json.dump({"format": self.FORMAT, "models": self.state}, handle, separators=(",", ":"))
                handle.write("\n")
            Path(temp_name).replace(self.state_path)
        finally:
            if temp_name and Path(temp_name).exists():
                Path(temp_name).unlink()

