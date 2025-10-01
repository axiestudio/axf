# -*- coding: utf-8 -*-
"""
📧 EMAIL SETTINGS CONFIGURATION
Enterprise-level email service configuration with SMTP support
"""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


class EmailSettings:
    """
    📧 Email service configuration settings
    
    Handles SMTP configuration for enterprise email functionality including:
    - Account verification emails
    - Password reset emails  
    - Professional email templates
    - SMTP authentication and security
    """
    
    def __init__(self):
        """Initialize email settings from environment variables"""

        # Ensure .env file is loaded if it exists (fallback mechanism)
        self._ensure_env_loaded()

        # SMTP Server Configuration
        self.SMTP_HOST: str = os.getenv("AXIESTUDIO_EMAIL_SMTP_HOST", "smtp.gmail.com")
        self.SMTP_PORT: int = int(os.getenv("AXIESTUDIO_EMAIL_SMTP_PORT", "587"))
        
        # SMTP Authentication
        self.SMTP_USER: Optional[str] = os.getenv("AXIESTUDIO_EMAIL_SMTP_USER")
        self.SMTP_PASSWORD: Optional[str] = os.getenv("AXIESTUDIO_EMAIL_SMTP_PASSWORD")
        
        # Email Configuration
        self.FROM_EMAIL: Optional[str] = os.getenv("AXIESTUDIO_EMAIL_FROM_EMAIL")
        self.FROM_NAME: str = os.getenv("AXIESTUDIO_EMAIL_FROM_NAME", "Axie Studio")
        
        # Email Templates Configuration
        self.COMPANY_NAME: str = os.getenv("AXIESTUDIO_COMPANY_NAME", "AxieStudio")
        self.COMPANY_URL: str = os.getenv("AXIESTUDIO_COMPANY_URL", "https://axiestudio.se")
        self.SUPPORT_EMAIL: str = os.getenv("AXIESTUDIO_SUPPORT_EMAIL", "support@axiestudio.se")
        
        # Security Configuration
        self.USE_TLS: bool = os.getenv("AXIESTUDIO_EMAIL_USE_TLS", "true").lower() == "true"
        self.USE_SSL: bool = os.getenv("AXIESTUDIO_EMAIL_USE_SSL", "false").lower() == "true"
        
        # Rate Limiting
        self.MAX_EMAILS_PER_HOUR: int = int(os.getenv("AXIESTUDIO_EMAIL_MAX_PER_HOUR", "100"))
        self.MAX_EMAILS_PER_DAY: int = int(os.getenv("AXIESTUDIO_EMAIL_MAX_PER_DAY", "1000"))
        
        # Verification Settings
        self.VERIFICATION_CODE_EXPIRY_MINUTES: int = int(os.getenv("AXIESTUDIO_VERIFICATION_EXPIRY_MINUTES", "10"))
        self.PASSWORD_RESET_EXPIRY_HOURS: int = int(os.getenv("AXIESTUDIO_PASSWORD_RESET_EXPIRY_HOURS", "1"))
        
        # Development/Testing
        self.EMAIL_ENABLED: bool = os.getenv("AXIESTUDIO_EMAIL_ENABLED", "true").lower() == "true"
        self.DEBUG_EMAIL: bool = os.getenv("AXIESTUDIO_EMAIL_DEBUG", "false").lower() == "true"
        
        # Fallback configuration for development
        self._setup_fallback_config()

    def _ensure_env_loaded(self) -> None:
        """Ensure .env file is loaded if it exists (fallback mechanism)"""
        # Only load if SMTP settings are not already in environment
        if not os.getenv("AXIESTUDIO_EMAIL_SMTP_HOST"):
            env_paths = [
                Path.cwd() / ".env",
                Path.cwd().parent / ".env",
                Path(__file__).parent.parent.parent.parent.parent.parent / ".env",  # axiestudio/.env
            ]

            for env_path in env_paths:
                if env_path.exists():
                    load_dotenv(env_path, override=False)  # Don't override existing env vars
                    break

    def _setup_fallback_config(self) -> None:
        """Setup fallback configuration for development environments"""

        # If no SMTP configuration is provided, use development defaults
        if not self.SMTP_USER and not self.SMTP_PASSWORD:
            # Development mode - log emails instead of sending
            self.EMAIL_ENABLED = False
            self.DEBUG_EMAIL = True

            # Set safe defaults
            self.FROM_EMAIL = "noreply@axiestudio.se"
            self.SMTP_HOST = "localhost"
            self.SMTP_PORT = 1025  # Common development SMTP port

        # Ensure FROM_EMAIL is set if SMTP is configured but FROM_EMAIL is missing
        elif self.SMTP_USER and self.SMTP_PASSWORD and not self.FROM_EMAIL:
            # This should not happen in production - log a warning
            import logging
            logging.warning("SMTP configured but AXIESTUDIO_EMAIL_FROM_EMAIL not set. Email sending may fail.")
            self.FROM_EMAIL = "noreply@axiestudio.se"  # Emergency fallback
    
    def is_configured(self) -> bool:
        """Check if email service is properly configured"""
        return bool(
            self.SMTP_HOST and 
            self.SMTP_USER and 
            self.SMTP_PASSWORD and 
            self.FROM_EMAIL and 
            "@" in self.FROM_EMAIL
        )
    
    def get_smtp_config(self) -> dict:
        """Get SMTP configuration dictionary"""
        return {
            "host": self.SMTP_HOST,
            "port": self.SMTP_PORT,
            "user": self.SMTP_USER,
            "password": self.SMTP_PASSWORD,
            "use_tls": self.USE_TLS,
            "use_ssl": self.USE_SSL,
        }
    
    def get_email_config(self) -> dict:
        """Get email configuration dictionary"""
        return {
            "from_email": self.FROM_EMAIL,
            "from_name": self.FROM_NAME,
            "company_name": self.COMPANY_NAME,
            "company_url": self.COMPANY_URL,
            "support_email": self.SUPPORT_EMAIL,
        }
    
    def __repr__(self) -> str:
        """String representation of email settings (without sensitive data)"""
        return (
            f"EmailSettings("
            f"smtp_host='{self.SMTP_HOST}', "
            f"smtp_port={self.SMTP_PORT}, "
            f"from_email='{self.FROM_EMAIL}', "
            f"configured={self.is_configured()}, "
            f"enabled={self.EMAIL_ENABLED}"
            f")"
        )


# Global email settings instance
email_settings = EmailSettings()


# Environment variable documentation
EMAIL_ENV_VARS = {
    "AXIESTUDIO_EMAIL_SMTP_HOST": "SMTP server hostname (default: smtp.gmail.com)",
    "AXIESTUDIO_EMAIL_SMTP_PORT": "SMTP server port (default: 587)",
    "AXIESTUDIO_EMAIL_SMTP_USER": "SMTP username/email address",
    "AXIESTUDIO_EMAIL_SMTP_PASSWORD": "SMTP password or app password",
    "AXIESTUDIO_EMAIL_FROM_EMAIL": "From email address (preferred, default: same as SMTP_USER)",
    "AXIESTUDIO_EMAIL_FROM": "From email address (legacy, use AXIESTUDIO_EMAIL_FROM_EMAIL instead)",
    "AXIESTUDIO_EMAIL_FROM_NAME": "From name (default: AxieStudio)",
    "AXIESTUDIO_COMPANY_NAME": "Company name for emails (default: AxieStudio)",
    "AXIESTUDIO_COMPANY_URL": "Company URL (default: https://axiestudio.se)",
    "AXIESTUDIO_SUPPORT_EMAIL": "Support email (default: support@axiestudio.se)",
    "AXIESTUDIO_EMAIL_USE_TLS": "Use TLS encryption (default: true)",
    "AXIESTUDIO_EMAIL_USE_SSL": "Use SSL encryption (default: false)",
    "AXIESTUDIO_EMAIL_MAX_PER_HOUR": "Max emails per hour (default: 100)",
    "AXIESTUDIO_EMAIL_MAX_PER_DAY": "Max emails per day (default: 1000)",
    "AXIESTUDIO_VERIFICATION_EXPIRY_MINUTES": "Verification code expiry (default: 10)",
    "AXIESTUDIO_PASSWORD_RESET_EXPIRY_HOURS": "Password reset expiry (default: 1)",
    "AXIESTUDIO_EMAIL_ENABLED": "Enable email sending (default: true)",
    "AXIESTUDIO_EMAIL_DEBUG": "Debug mode - log emails (default: false)",
}


def get_email_settings() -> EmailSettings:
    """Get the global email settings instance"""
    return email_settings


def validate_email_configuration() -> tuple[bool, list[str]]:
    """
    Validate email configuration and return status with issues
    
    Returns:
        tuple: (is_valid, list_of_issues)
    """
    issues = []
    
    if not email_settings.SMTP_HOST:
        issues.append("SMTP_HOST not configured")
    
    if not email_settings.SMTP_USER:
        issues.append("SMTP_USER not configured")
    
    if not email_settings.SMTP_PASSWORD:
        issues.append("SMTP_PASSWORD not configured")
    
    if not email_settings.FROM_EMAIL:
        issues.append("FROM_EMAIL not configured")
    elif "@" not in email_settings.FROM_EMAIL:
        issues.append("FROM_EMAIL is not a valid email address")
    
    if email_settings.SMTP_PORT not in [25, 465, 587, 2525]:
        issues.append(f"SMTP_PORT {email_settings.SMTP_PORT} is not a standard SMTP port")
    
    return len(issues) == 0, issues


# Export the main class and utility functions
__all__ = [
    "EmailSettings",
    "email_settings", 
    "get_email_settings",
    "validate_email_configuration",
    "EMAIL_ENV_VARS"
]
