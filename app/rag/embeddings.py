from __future__ import annotations

from typing import List

from openai import OpenAI

from app.core.config import settings


_client: OpenAI | None = None


def _client_instance() -> OpenAI:
    global _client
    if _client is None:
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured.")
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client


def embed_texts(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []

    client = _client_instance()
    response = client.embeddings.create(model=settings.embedding_model, input=texts)
    return [item.embedding for item in response.data]
