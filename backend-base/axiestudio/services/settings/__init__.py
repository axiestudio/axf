from . import factory, service
from .base import Settings
from .email import EmailSettings, email_settings

# Create a global settings instance
settings = Settings()

__all__ = ["factory", "service", "settings", "Settings", "EmailSettings", "email_settings"]
