"""Failures raised by gateway provider adapters (chat, embedding, rerank) and
by online retrieval."""

from __future__ import annotations

from genql.domain.errors.base import GenqlError


class ChatProviderError(GenqlError):
    """A ChatProvider implementation could not complete a call."""


class EmbeddingProviderError(GenqlError):
    """An EmbeddingProvider implementation could not complete a call."""


class RerankProviderError(GenqlError):
    """A RerankProvider implementation could not complete a call."""


class RetrievalError(GenqlError):
    """Hybrid retrieval or reranking could not complete. Runs online, not during discovery."""
