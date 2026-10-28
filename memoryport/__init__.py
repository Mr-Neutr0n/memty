"""Portable smart routing and memory utilities for NexorAI."""

from .memory import MongoSyncedMemoryStore, PortableMemoryStore
from .router import ModelSpec, RouteDecision, SmartRouter
from .ledger import MemoryLedger
from .evaluation import evaluate_cases
from .vault import export_nxvault, import_nxvault
from .mongo_ledger import MongoMemoryLedger
from .extractor import MemoryExtractor
from .sdk import ChatResponse, ModelConfig, NexorAI, RouteResult, load_client
from .embeddings import (EmbeddingAdapter, EmbeddingConfig, EmbeddingError,
                         GeminiEmbeddingAdapter, OpenAICompatibleEmbeddingAdapter)

__all__ = ["ChatResponse", "EmbeddingAdapter", "EmbeddingConfig", "EmbeddingError", "GeminiEmbeddingAdapter",
           "MemoryExtractor", "OpenAICompatibleEmbeddingAdapter",
           "MemoryLedger", "ModelConfig", "ModelSpec", "MongoMemoryLedger",
           "MongoSyncedMemoryStore", "NexorAI", "PortableMemoryStore", "RouteDecision", "RouteResult",
           "SmartRouter", "evaluate_cases", "export_nxvault", "import_nxvault", "load_client"]

