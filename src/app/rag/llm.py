"""Gemini chat model built through LlamaIndex. Used by /ask and by the chat stream."""

from fastapi import HTTPException
from google.genai import types
from llama_index.core.llms import ChatMessage, MessageRole
from llama_index.llms.google_genai import GoogleGenAI

from app.config.settings import Settings

GENERATION_TIMEOUT_MS = 30_000


def build_llm(settings: Settings, timeout_ms: int = GENERATION_TIMEOUT_MS) -> GoogleGenAI:
    """Return the answer model. Uses Vertex AI when a project is set, otherwise the API key."""
    options = types.HttpOptions(api_version="v1", timeout=timeout_ms)
    if settings.google_cloud_project:
        return GoogleGenAI(
            model=settings.gemini_model,
            vertexai_config={
                "project": settings.google_cloud_project,
                "location": settings.google_cloud_location,
            },
            http_options=options,
        )
    if key := settings.gemini_api_key.get_secret_value().strip():
        return GoogleGenAI(model=settings.gemini_model, api_key=key, http_options=options)
    raise HTTPException(
        status_code=503,
        detail="Set GEMINI_API_KEY for local development or configure Vertex AI credentials.",
    )


def make_messages(system: str, user: str) -> list[ChatMessage]:
    """Build a system message followed by one user message."""
    return [
        ChatMessage(role=MessageRole.SYSTEM, content=system),
        ChatMessage(role=MessageRole.USER, content=user),
    ]
