"""Application configuration, read from environment variables and the repo .env file."""

from app.config.settings import Settings, get_settings

__all__ = ["Settings", "get_settings"]
