"""Small standard-library embedding clients for portable semantic memory."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class EmbeddingError(RuntimeError):
    """An embedding provider could not return a usable vector."""


@dataclass(frozen=True)
class EmbeddingConfig:
    provider: str = "openai-compatible"
    model: str = "nomic-embed-text"
    base_url: str = ""
    api_key_env: str = ""
    timeout_seconds: float = 20.0

    def __post_init__(self) -> None:
        if self.provider not in {"openai-compatible", "openrouter", "ollama", "lm-studio", "gemini"}:
            raise ValueError("unsupported embedding provider")
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", self.model) or not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("embedding model and timeout must be valid")
        if self.api_key_env and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self.api_key_env):
            raise ValueError("embedding api_key_env must be a valid environment variable name")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "EmbeddingConfig":
        accepted = {item.name for item in cls.__dataclass_fields__.values()}
        return cls(**{key: item for key, item in value.items() if key in accepted})

    @property
    def cache_key(self) -> str:
        identity = f"{self.provider}\0{self.model}\0{self.base_url.rstrip('/')}"
        return f"{self.provider}:{self.model}:{hashlib.sha256(identity.encode()).hexdigest()[:16]}"


class EmbeddingAdapter(Protocol):
    def embed(self, text: str, config: EmbeddingConfig) -> list[float]: ...


def _request(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=body, headers={"Content-Type": "application/json", **headers}, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise EmbeddingError("Could not get an embedding from the configured provider.") from None
    if not isinstance(result, dict):
        raise EmbeddingError("Embedding provider returned an invalid response.")
    return result


def _base(config: EmbeddingConfig) -> str:
    defaults = {
        "openai-compatible": "https://api.openai.com/v1",
        "openrouter": "https://openrouter.ai/api/v1",
        "ollama": "http://localhost:11434/v1",
        "lm-studio": "http://localhost:1234/v1",
        "gemini": "https://generativelanguage.googleapis.com",
    }
    base = (config.base_url or defaults.get(config.provider, "")).rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise EmbeddingError("Embedding base_url must be an HTTP or HTTPS URL.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise EmbeddingError("Use an environment variable for credentials; keep base_url free of query parameters.")
    if parsed.scheme == "http" and parsed.hostname.lower() not in {"localhost", "127.0.0.1", "::1"}:
        raise EmbeddingError("Use HTTPS for remote embedding providers; HTTP is allowed only on loopback.")
    return base


def _key(config: EmbeddingConfig) -> str:
    key = os.getenv(config.api_key_env, "").strip() if config.api_key_env else ""
    required = config.provider in {"gemini"}
    if required and not key:
        raise EmbeddingError(f"Set {config.api_key_env or 'api_key_env'} for the embedding provider.")
    return key


class OpenAICompatibleEmbeddingAdapter:
    """OpenAI-compatible embeddings, including local Ollama and LM Studio."""

    def embed(self, text: str, config: EmbeddingConfig) -> list[float]:
        key = _key(config)
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        response = _request(_base(config) + "/embeddings", {"model": config.model, "input": text},
                            headers, config.timeout_seconds)
        rows = response.get("data") or []
        vector = rows[0].get("embedding") if rows and isinstance(rows[0], dict) else None
        return _validate_vector(vector)


class GeminiEmbeddingAdapter:
    """Gemini embedContent endpoint with a separately configured embedding model."""

    def embed(self, text: str, config: EmbeddingConfig) -> list[float]:
        key = _key(config)
        base = _base(config) if config.base_url else "https://generativelanguage.googleapis.com"
        base = base.removesuffix("/v1beta").removesuffix("/v1")
        endpoint = f"{base}/v1beta/models/{config.model}:embedContent"
        response = _request(endpoint, {"content": {"parts": [{"text": text}]}},
                            {"x-goog-api-key": key}, config.timeout_seconds)
        vector = (response.get("embedding") or {}).get("values")
        return _validate_vector(vector)


def _validate_vector(value: Any) -> list[float]:
    if not isinstance(value, list) or not value or len(value) > 32768:
        raise EmbeddingError("Embedding provider returned no usable vector.")
    try:
        vector = [float(item) for item in value]
    except (TypeError, ValueError):
        raise EmbeddingError("Embedding provider returned an invalid vector.") from None
    if not all(math.isfinite(item) for item in vector):
        raise EmbeddingError("Embedding provider returned non-finite vector values.")
    return vector


