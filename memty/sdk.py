"""Public Memty SDK surface for model routing and multi-provider chat.

The implementation remains in the compatibility module while existing
applications migrate; new applications should import it through ``memty``.
"""

from memoryport.sdk import (
    AnthropicAdapter,
    ChatResponse,
    ConfigurationError,
    GeminiInteractionsAdapter,
    Memty,
    MemtyError,
    ModelConfig,
    NoModelAvailable,
    OpenAICompatibleAdapter,
    ProviderAdapter,
    ProviderRequestError,
    RouteResult,
    load_client,
)
from memoryport.embeddings import (
    EmbeddingAdapter,
    EmbeddingConfig,
    EmbeddingError,
    GeminiEmbeddingAdapter,
    OpenAICompatibleEmbeddingAdapter,
)
from memoryport.extractor import MemoryExtractor

__all__ = [
    "AnthropicAdapter", "ChatResponse", "ConfigurationError", "EmbeddingAdapter",
    "EmbeddingConfig", "EmbeddingError", "GeminiEmbeddingAdapter",
    "GeminiInteractionsAdapter", "Memty", "MemtyError", "MemoryExtractor",
    "ModelConfig", "NoModelAvailable", "OpenAICompatibleAdapter",
    "OpenAICompatibleEmbeddingAdapter", "ProviderAdapter", "ProviderRequestError",
    "RouteResult", "load_client",
]
