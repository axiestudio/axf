"""
Enterprise Email Service with Professional Templates
Clean, professional email templates without emojis
"""

import smtplib
import secrets
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, Any
from enum import Enum

from axiestudio.logging import logger

try:
    import resend
    RESEND_SDK_AVAILABLE = True
except ImportError:
    RESEND_SDK_AVAILABLE = False
    resend = None

from axiestudio.services.settings.email import EmailSettings
from axiestudio.services.deps import get_settings_service


class EmailMethod(Enum):
    """Email sending methods"""
    SDK = "sdk"
    SMTP = "smtp"


class EmailService:
    """
    Enterprise-grade dual email service with Resend SDK + SMTP fallback.

    Features:
    - Resend Python SDK (primary method)
    - SMTP fallback (secondary method)
    - Professional email templates without emojis
    - Email verification codes
    - Password reset emails
    - Intelligent method switching
    - Enhanced error handling and logging
    """

    def __init__(self):
        self.settings = EmailSettings()
        self.preferred_method = EmailMethod.SDK if RESEND_SDK_AVAILABLE else EmailMethod.SMTP
        self._validate_configuration()
        self._log_configuration_debug()

    def _validate_configuration(self) -> None:
        """Validate email configuration on startup."""
        if not self.settings.SMTP_HOST:
            logger.warning("SMTP_HOST not configured. Email functionality will be disabled.")
        
        if not self.settings.SMTP_USER or not self.settings.SMTP_PASSWORD:
            logger.warning("SMTP credentials not configured. Email functionality will be disabled.")
        
        if not self.settings.FROM_EMAIL:
            logger.warning("FROM_EMAIL not configured. Email functionality will be disabled.")

    def _log_configuration_debug(self) -> None:
        """Log email configuration for debugging purposes."""
        logger.debug("🚀 DUAL EMAIL SERVICE CONFIGURATION:")
        logger.debug(f"  📧 Resend SDK Available: {RESEND_SDK_AVAILABLE}")
        logger.debug(f"  🎯 Preferred Method: {self.preferred_method.value}")
        logger.debug(f"  🔧 SMTP_HOST: {self.settings.SMTP_HOST}")
        logger.debug(f"  🔧 SMTP_PORT: {self.settings.SMTP_PORT}")
        logger.debug(f"  🔧 SMTP_USER: {self.settings.SMTP_USER}")
        logger.debug(f"  🔧 SMTP_PASSWORD: {'*' * len(self.settings.SMTP_PASSWORD) if self.settings.SMTP_PASSWORD else 'NOT SET'}")
        logger.debug(f"  📨 FROM_EMAIL: {self.settings.FROM_EMAIL}")
        logger.debug(f"  👤 FROM_NAME: {self.settings.FROM_NAME}")
        logger.debug(f"  ⚡ EMAIL_ENABLED: {self.settings.EMAIL_ENABLED}")
        logger.debug(f"  ✅ Configuration Valid: {self.settings.is_configured()}")

    async def test_email_methods(self) -> Dict[str, Any]:
        """Test both email methods and return status."""
        results = {
            "resend_sdk": {"available": RESEND_SDK_AVAILABLE, "configured": False},
            "smtp": {"available": True, "configured": False}
        }

        # Test Resend SDK configuration
        if RESEND_SDK_AVAILABLE and self.settings.SMTP_PASSWORD:
            try:
                resend.api_key = self.settings.SMTP_PASSWORD
                results["resend_sdk"]["configured"] = True
                logger.debug("✅ Resend SDK configured successfully")
            except Exception as e:
                logger.debug(f"❌ Resend SDK configuration failed: {e}")

        # Test SMTP configuration
        if all([self.settings.SMTP_HOST, self.settings.SMTP_USER, self.settings.SMTP_PASSWORD]):
            results["smtp"]["configured"] = True
            logger.debug("✅ SMTP configured successfully")
        else:
            logger.debug("❌ SMTP configuration incomplete")

        return results

    async def health_check(self) -> Dict[str, Any]:
        """Check email service health."""
        try:
            # Test both email methods
            method_results = await self.test_email_methods()

            health_status = {
                "service": "email_dual",
                "status": "healthy",
                "preferred_method": self.preferred_method.value,
                "methods": method_results,
                "smtp_host": self.settings.SMTP_HOST,
                "smtp_port": self.settings.SMTP_PORT,
                "from_email": self.settings.FROM_EMAIL,
                "issues": []
            }

            if not self.settings.SMTP_HOST:
                health_status["issues"].append("SMTP_HOST not configured")
                health_status["status"] = "degraded"

            if not self.settings.SMTP_USER or not self.settings.SMTP_PASSWORD:
                health_status["issues"].append("SMTP credentials not configured")
                health_status["status"] = "degraded"

            if not self.settings.FROM_EMAIL or "@" not in self.settings.FROM_EMAIL:
                health_status["issues"].append("Invalid FROM_EMAIL configuration")
                health_status["status"] = "degraded"

            return health_status

        except Exception as e:
            logger.error(f"Email service health check failed: {e}")
            return {
                "service": "email",
                "status": "unhealthy",
                "error": str(e)
            }
    
    def generate_verification_token(self) -> str:
        """Generate a secure verification token."""
        return secrets.token_urlsafe(32)
    
    def get_verification_expiry(self) -> datetime:
        """Get verification token expiry time (24 hours from now)."""
        return datetime.now(timezone.utc) + timedelta(hours=24)
    
    async def send_verification_code_email(self, email: str, username: str, verification_code: str) -> bool:
        """Send 6-digit verification code email with professional template."""
        try:
            subject = "Verify your AxieStudio account"
            
            html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Verify your AxieStudio account</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #1a202c;
            max-width: 600px;
            margin: 0 auto;
            padding: 0;
            background-color: #f7fafc;
        }}
        .email-container {{
            background: #ffffff;
            margin: 20px;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 40px 40px 30px;
            text-align: center;
        }}

        .header h1 {{
            color: white;
            margin: 0;
            font-size: 28px;
            font-weight: 600;
        }}
        .header p {{
            color: rgba(255, 255, 255, 0.9);
            margin: 8px 0 0;
            font-size: 16px;
        }}
        .content {{
            padding: 40px;
        }}
        .verification-code {{
            background: #f7fafc;
            border: 2px solid #e2e8f0;
            color: #2d3748;
            font-size: 36px;
            font-weight: 700;
            text-align: center;
            padding: 24px;
            border-radius: 8px;
            letter-spacing: 6px;
            margin: 30px 0;
            font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Roboto Mono', monospace;
        }}
        .footer {{
            background-color: #f7fafc;
            padding: 30px 40px;
            text-align: center;
            border-top: 1px solid #e2e8f0;
            color: #718096;
            font-size: 14px;
        }}
    </style>
</head>
<body>
    <div class="email-container">
        <div class="header">
            <img src="https://flow.axiestudio.se/logo192.png" alt="AxieStudio Logo" style="width: 48px; height: 48px; margin: 0 auto 16px auto; display: block; border-radius: 8px;" onerror="this.style.display='none'; this.nextElementSibling.style.display='block';">
            <div class="logo" style="display: none;">AX</div>
            <h1>Email Verification</h1>
            <p>Welcome to AxieStudio</p>
        </div>

        <div class="content">
            <p>Hello <strong>{username}</strong>,</p>
            <p>Thank you for signing up for AxieStudio. To complete your account setup, please use the verification code below:</p>

            <div class="verification-code">
                {verification_code}
            </div>

            <p style="text-align: center; color: #718096; font-size: 14px; margin: 16px 0;">
                This code expires in 10 minutes
            </p>

            <div style="background-color: #edf2f7; border-left: 4px solid #4299e1; padding: 16px; margin: 24px 0; border-radius: 4px;">
                <h4 style="margin: 0 0 8px; color: #2b6cb0; font-size: 16px;">How to verify your account:</h4>
                <ol style="margin: 8px 0 0; padding-left: 20px; color: #4a5568;">
                    <li>Return to the AxieStudio verification page</li>
                    <li>Enter the 6-digit code above</li>
                    <li>Click "Verify Account" to complete setup</li>
                </ol>
            </div>

            <div style="background-color: #fef5e7; border-left: 4px solid #ed8936; padding: 16px; margin: 24px 0; border-radius: 4px;">
                <p style="margin: 0; color: #744210; font-weight: 500;"><strong>Security Notice:</strong> Never share this code with anyone.</p>
            </div>

            <p style="color: #718096; font-size: 14px; margin-top: 30px;">
                Didn't request this verification? You can safely ignore this email.
            </p>
        </div>

        <div class="footer">
            <p><strong>AxieStudio</strong> - Building the future of AI workflows</p>
            <p>Visit us at <a href="https://axiestudio.se" style="color: #4299e1; text-decoration: none;">axiestudio.se</a></p>
        </div>
    </div>
</body>
</html>
            """

            text_body = f"""
AxieStudio - Email Verification

Hello {username},

Thank you for signing up for AxieStudio. To complete your account setup, please use the verification code below:

Verification Code: {verification_code}

This code expires in 10 minutes.

How to verify your account:
1. Return to the AxieStudio verification page
2. Enter the 6-digit code above
3. Click "Verify Account" to complete setup

Security Notice: Never share this code with anyone.

Didn't request this verification? You can safely ignore this email.

---
AxieStudio - Building the future of AI workflows
Visit us at: https://axiestudio.se
            """

            success = await self._send_email(email, subject, text_body, html_body)

            if success:
                logger.info(f"Verification code email sent successfully to {email}")
            else:
                logger.error(f"Failed to send verification code email to {email}")

            return success

        except Exception as e:
            logger.exception(f"Error sending verification code email to {email}: {e}")
            return False

    async def send_verification_email(self, email: str, username: str, token: str) -> bool:
        """Send email verification email (legacy token-based)."""
        try:
            # Get frontend URL from settings
            settings_service = get_settings_service()
            frontend_url = getattr(settings_service.settings, 'frontend_url', 'https://flow.axiestudio.se')
            
            # Create verification link
            verification_link = f"{frontend_url}/verify-email?token={token}"
            
            subject = "Verify your AxieStudio email address"
            
            # Use same professional template but with link instead of code
            html_body = f"""
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
    <title>Verify your AxieStudio email</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #f8fafc;">
        <tr>
            <td align="center" style="padding: 20px 0;">
                <table border="0" cellpadding="0" cellspacing="0" width="600" style="background-color: #ffffff; border-radius: 12px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.07);">
                    <!-- Header -->
                    <tr>
                        <td style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 40px 40px 30px; text-align: center; border-radius: 12px 12px 0 0;">
                            <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                <tr>
                                    <td align="center">
                                        <div style="background: rgba(255, 255, 255, 0.15); width: 64px; height: 64px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; margin-bottom: 20px;">
                                            <span style="color: white; font-size: 28px; font-weight: bold;">✉️</span>
                                        </div>
                                        <h1 style="color: white; margin: 0 0 8px 0; font-size: 28px; font-weight: 600; line-height: 1.2;">Email Verification</h1>
                                        <p style="color: rgba(255, 255, 255, 0.9); margin: 0; font-size: 16px; line-height: 1.4;">Welcome to AxieStudio</p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Content -->
                    <tr>
                        <td style="padding: 40px;">
                            <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                <tr>
                                    <td>
                                        <p style="margin: 0 0 20px 0; font-size: 16px; line-height: 1.6; color: #374151;">Hello <strong>{username}</strong>,</p>
                                        <p style="margin: 0 0 32px 0; font-size: 16px; line-height: 1.6; color: #374151;">Thank you for signing up for AxieStudio! Please click the button below to verify your email address and activate your account.</p>

                                        <!-- Verify Button -->
                                        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="margin: 32px 0;">
                                            <tr>
                                                <td align="center">
                                                    <a href="{verification_link}" style="display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 16px 40px; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 16px; box-shadow: 0 4px 6px rgba(102, 126, 234, 0.25);">Verify Email Address</a>
                                                </td>
                                            </tr>
                                        </table>

                                        <!-- Alternative Link -->
                                        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #f9fafb; border-radius: 8px; margin: 24px 0;">
                                            <tr>
                                                <td style="padding: 20px;">
                                                    <p style="margin: 0 0 8px 0; font-size: 14px; color: #6b7280; font-weight: 600;">Can't click the button? Copy and paste this link:</p>
                                                    <p style="margin: 0; font-size: 14px; color: #3b82f6; word-break: break-all;">{verification_link}</p>
                                                </td>
                                            </tr>
                                        </table>

                                        <!-- Info Note -->
                                        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #f0f9ff; border-left: 4px solid #0ea5e9; border-radius: 4px; margin: 24px 0;">
                                            <tr>
                                                <td style="padding: 16px;">
                                                    <p style="margin: 0; color: #0c4a6e; font-size: 14px; line-height: 1.5;"><strong>💡 Note:</strong> Didn't request this verification? You can safely ignore this email.</p>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="background-color: #f9fafb; padding: 32px 40px; text-align: center; border-top: 1px solid #e5e7eb; border-radius: 0 0 12px 12px;">
                            <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                <tr>
                                    <td align="center">
                                        <p style="margin: 0 0 8px 0; font-weight: 600; color: #374151; font-size: 16px;">AxieStudio</p>
                                        <p style="margin: 0; color: #6b7280; font-size: 14px;">Building the future of AI workflows</p>
                                        <p style="margin: 12px 0 0 0; color: #6b7280; font-size: 14px;">Visit us at <a href="https://flow.axiestudio.se" style="color: #3b82f6; text-decoration: none;">flow.axiestudio.se</a></p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
            """

            text_body = f"""
AxieStudio - Email Verification

Hello {username},

Thank you for signing up for AxieStudio! Please click the link below to verify your email address and activate your account:

{verification_link}

Didn't request this verification? You can safely ignore this email.

---
AxieStudio - Building the future of AI workflows
Visit us at: https://flow.axiestudio.se
            """

            return await self._send_email(email, subject, text_body, html_body)

        except Exception as e:
            logger.error(f"Failed to send verification email to {email}: {e}")
            return False

    async def send_password_reset_email(self, email: str, username: str, token: str, client_ip: str = "unknown") -> bool:
        """Send password reset email with professional template."""
        try:
            # Get frontend URL from settings
            settings_service = get_settings_service()
            frontend_url = getattr(settings_service.settings, 'frontend_url', 'https://flow.axiestudio.se')

            # Create password reset link
            reset_link = f"{frontend_url}/reset-password?token={token}"

            subject = "Reset your AxieStudio password"

            html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reset your AxieStudio password</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #1a202c;
            max-width: 600px;
            margin: 0 auto;
            padding: 0;
            background-color: #f7fafc;
        }}
        .email-container {{
            background: #ffffff;
            margin: 20px;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
        }}
        .header {{
            background: linear-gradient(135deg, #dc2626 0%, #b91c1c 100%);
            padding: 40px 40px 30px;
            text-align: center;
        }}

        .header h1 {{
            color: white;
            margin: 0;
            font-size: 28px;
            font-weight: 600;
        }}
        .header p {{
            color: rgba(255, 255, 255, 0.9);
            margin: 8px 0 0;
            font-size: 16px;
        }}
        .content {{
            padding: 40px;
        }}
        .reset-button {{
            display: inline-block;
            background: linear-gradient(135deg, #dc2626 0%, #b91c1c 100%);
            color: white;
            padding: 16px 32px;
            text-decoration: none;
            border-radius: 8px;
            font-weight: 600;
            font-size: 16px;
            margin: 24px 0;
        }}
        .footer {{
            background-color: #f7fafc;
            padding: 30px 40px;
            text-align: center;
            border-top: 1px solid #e2e8f0;
            color: #718096;
            font-size: 14px;
        }}
    </style>
</head>
<body>
    <div class="email-container">
        <div class="header">
            <img src="https://flow.axiestudio.se/logo192.png" alt="AxieStudio Logo" style="width: 48px; height: 48px; margin: 0 auto 16px auto; display: block; border-radius: 8px;" onerror="this.style.display='none'; this.nextElementSibling.style.display='block';">
            <div class="logo" style="display: none;">AX</div>
            <h1>Password Reset</h1>
            <p>Secure password reset for your account</p>
        </div>

        <div class="content">
            <p>Hello <strong>{username}</strong>,</p>
            <p>We received a request to reset your password for your AxieStudio account. Click the button below to reset your password:</p>

            <div style="text-align: center; margin: 30px 0;">
                <a href="{reset_link}" class="reset-button">
                    Reset Password
                </a>
            </div>

            <div style="background-color: #fef5e7; border-left: 4px solid #f59e0b; padding: 16px; margin: 24px 0; border-radius: 4px;">
                <p style="margin: 0; color: #92400e; font-weight: 500;"><strong>Important:</strong> This password reset link will expire in 24 hours.</p>
            </div>

            <p><strong>What happens next:</strong></p>
            <ol style="color: #4a5568;">
                <li>Click the reset button above</li>
                <li>You'll be logged in automatically</li>
                <li>Go to Settings to change your password</li>
                <li>Your new password will be saved securely</li>
            </ol>

            <div style="background-color: #fee2e2; border-left: 4px solid #dc2626; padding: 16px; margin: 24px 0; border-radius: 4px;">
                <p style="margin: 0; color: #991b1b; font-weight: 500;"><strong>Security Notice:</strong> If you didn't request this password reset, please ignore this email.</p>
                <p style="margin: 8px 0 0 0; color: #991b1b; font-size: 12px;">Request originated from IP: {client_ip}</p>
            </div>
        </div>

        <div class="footer">
            <p><strong>AxieStudio</strong> - Building the future of AI workflows</p>
            <p>Visit us at <a href="https://axiestudio.se" style="color: #4299e1; text-decoration: none;">axiestudio.se</a></p>
        </div>
    </div>
</body>
</html>
            """

            text_body = f"""
AxieStudio - Password Reset

Hello {username},

We received a request to reset your password for your AxieStudio account.

To reset your password, visit this link:
{reset_link}

IMPORTANT: This password reset link will expire in 24 hours.

What happens next:
1. Click the reset link above
2. You'll be logged in automatically
3. Go to Settings to change your password
4. Your new password will be saved securely

Security Notice: If you didn't request this password reset, please ignore this email.
Request originated from IP: {client_ip}

---
AxieStudio - Building the future of AI workflows
Visit us at: https://axiestudio.se
            """

            return await self._send_email(email, subject, text_body, html_body)

        except Exception as e:
            logger.error(f"Failed to send password reset email to {email}: {e}")
            return False

    async def send_temporary_password_email(self, email: str, username: str, temp_password: str, client_ip: str = "unknown") -> bool:
        """Send temporary password email with professional template."""
        try:
            subject = "Your AxieStudio Temporary Password"

            html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Your AxieStudio Temporary Password</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #1a202c;
            max-width: 600px;
            margin: 0 auto;
            padding: 0;
            background-color: #f7fafc;
        }}
        .email-container {{
            background-color: #ffffff;
            margin: 20px auto;
            border-radius: 12px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px 20px;
            text-align: center;
        }}

        .content {{
            padding: 40px;
        }}
        .password-box {{
            background-color: #f8fafc;
            border: 2px solid #e2e8f0;
            border-radius: 8px;
            padding: 24px;
            margin: 24px 0;
            text-align: center;
        }}
        .temp-password {{
            font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
            font-size: 24px;
            font-weight: bold;
            color: #2d3748;
            background-color: #ffffff;
            padding: 16px;
            border-radius: 6px;
            border: 2px solid #4299e1;
            margin: 16px 0;
            letter-spacing: 2px;
        }}
        .login-button {{
            display: inline-block;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 14px 32px;
            text-decoration: none;
            border-radius: 8px;
            font-weight: 600;
            margin: 20px 0;
        }}
        .warning-box {{
            background-color: #fef5e7;
            border-left: 4px solid #f59e0b;
            padding: 16px;
            margin: 24px 0;
            border-radius: 4px;
        }}
        .footer {{
            background-color: #f7fafc;
            padding: 30px;
            text-align: center;
            color: #718096;
            font-size: 14px;
        }}
    </style>
</head>
<body>
    <div class="email-container">
        <div class="header">
            <img src="https://flow.axiestudio.se/logo192.png" alt="AxieStudio Logo" style="width: 48px; height: 48px; margin: 0 auto 16px auto; display: block; border-radius: 8px;">
            <h1>Password Reset</h1>
            <p>Your temporary password is ready</p>
        </div>

        <div class="content">
            <p>Hello <strong>{username}</strong>,</p>
            <p>We've generated a temporary password for your AxieStudio account. Use this to log in:</p>

            <div class="password-box">
                <p style="margin: 0 0 8px 0; font-weight: 600; color: #4a5568;">Temporary Password (Valid for 24 hours)</p>
                <div class="temp-password">{temp_password}</div>
                <p style="margin: 8px 0 0 0; font-size: 14px; color: #718096;">Copy this password exactly as shown</p>
            </div>

            <div style="text-align: center; margin: 30px 0;">
                <a href="https://flow.axiestudio.se/login" class="login-button">
                    Login to AxieStudio
                </a>
            </div>

            <div class="warning-box">
                <p style="margin: 0; color: #92400e; font-weight: 500;"><strong>Important:</strong> This temporary password expires in 24 hours. You will be required to change it after logging in for security.</p>
            </div>

            <div style="background-color: #e6fffa; border-left: 4px solid #38b2ac; padding: 16px; margin: 24px 0; border-radius: 4px;">
                <p style="margin: 0; color: #234e52; font-weight: 500;"><strong>Login Instructions:</strong></p>
                <ol style="margin: 8px 0 0 0; color: #234e52;">
                    <li>Go to the login page</li>
                    <li>Enter your username: <strong>{username}</strong></li>
                    <li>Enter the temporary password above</li>
                    <li>You'll be prompted to create a new password</li>
                </ol>
            </div>

            <div style="background-color: #fee2e2; border-left: 4px solid #dc2626; padding: 16px; margin: 24px 0; border-radius: 4px;">
                <p style="margin: 0; color: #991b1b; font-weight: 500;"><strong>Security Notice:</strong> If you didn't request this password reset, please contact support immediately.</p>
                <p style="margin: 8px 0 0 0; color: #991b1b; font-size: 12px;">Request originated from IP: {client_ip}</p>
            </div>
        </div>

        <div class="footer">
            <p><strong>AxieStudio</strong> - Building the future of AI workflows</p>
            <p>Visit us at <a href="https://axiestudio.se" style="color: #4299e1; text-decoration: none;">axiestudio.se</a></p>
        </div>
    </div>
</body>
</html>
            """

            text_body = f"""
AxieStudio - Password Reset

Hello {username},

We've generated a temporary password for your AxieStudio account.

Temporary Password (Valid for 24 hours): {temp_password}

Login Instructions:
1. Go to: https://flow.axiestudio.se/login
2. Username: {username}
3. Password: {temp_password}
4. You'll be prompted to create a new password

IMPORTANT: This temporary password expires in 24 hours. You will be required to change it after logging in for security.

Security Notice: If you didn't request this password reset, please contact support immediately.
Request originated from IP: {client_ip}

---
AxieStudio - Building the future of AI workflows
Visit us at: https://axiestudio.se
            """

            return await self._send_email(email, subject, text_body, html_body)

        except Exception as e:
            logger.error(f"Failed to send temporary password email to {email}: {e}")
            return False

    async def send_new_login_detected_email(self, email: str, username: str, client_ip: str = "unknown", location: str = "unknown", device: str = "unknown") -> bool:
        """Send new login detection email with professional template."""
        try:
            subject = "New sign-in detected to your AxieStudio account"

            # Get current time for the email
            login_time = datetime.now(timezone.utc).strftime("%B %d, %Y at %I:%M %p UTC")

            html_body = f"""
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
    <title>New sign-in detected - AxieStudio</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #f8fafc;">
        <tr>
            <td align="center" style="padding: 20px 0;">
                <table border="0" cellpadding="0" cellspacing="0" width="600" style="background-color: #ffffff; border-radius: 12px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.07);">
                    <!-- Header -->
                    <tr>
                        <td style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 40px 40px 30px; text-align: center; border-radius: 12px 12px 0 0;">
                            <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                <tr>
                                    <td align="center">
                                        <div style="background: rgba(255, 255, 255, 0.15); width: 64px; height: 64px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; margin-bottom: 20px;">
                                            <span style="color: white; font-size: 28px; font-weight: bold;">🔒</span>
                                        </div>
                                        <h1 style="color: white; margin: 0 0 8px 0; font-size: 28px; font-weight: 600; line-height: 1.2;">New Sign-in Detected</h1>
                                        <p style="color: rgba(255, 255, 255, 0.9); margin: 0; font-size: 16px; line-height: 1.4;">Security notification for your account</p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Content -->
                    <tr>
                        <td style="padding: 40px;">
                            <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                <tr>
                                    <td>
                                        <p style="margin: 0 0 20px 0; font-size: 16px; line-height: 1.6; color: #374151;">Hello <strong>{username}</strong>,</p>
                                        <p style="margin: 0 0 24px 0; font-size: 16px; line-height: 1.6; color: #374151;">We detected a new sign-in to your AxieStudio account. If this was you, you can safely ignore this email.</p>

                                        <!-- Security Alert -->
                                        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #fef3cd; border: 1px solid #f59e0b; border-radius: 8px; margin: 24px 0;">
                                            <tr>
                                                <td style="padding: 20px; text-align: center;">
                                                    <p style="margin: 0; font-weight: 600; color: #92400e; font-size: 16px;">⚠️ New sign-in on {login_time}</p>
                                                </td>
                                            </tr>
                                        </table>

                                        <!-- Login Details -->
                                        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #f9fafb; border-radius: 8px; margin: 24px 0;">
                                            <tr>
                                                <td style="padding: 24px;">
                                                    <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                                        <tr>
                                                            <td style="padding: 8px 0; border-bottom: 1px solid #e5e7eb;">
                                                                <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                                                    <tr>
                                                                        <td style="font-weight: 600; color: #6b7280; font-size: 14px;">Account:</td>
                                                                        <td align="right" style="color: #374151; font-size: 14px;">{email}</td>
                                                                    </tr>
                                                                </table>
                                                            </td>
                                                        </tr>
                                                        <tr>
                                                            <td style="padding: 8px 0; border-bottom: 1px solid #e5e7eb;">
                                                                <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                                                    <tr>
                                                                        <td style="font-weight: 600; color: #6b7280; font-size: 14px;">Time:</td>
                                                                        <td align="right" style="color: #374151; font-size: 14px;">{login_time}</td>
                                                                    </tr>
                                                                </table>
                                                            </td>
                                                        </tr>
                                                        <tr>
                                                            <td style="padding: 8px 0; border-bottom: 1px solid #e5e7eb;">
                                                                <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                                                    <tr>
                                                                        <td style="font-weight: 600; color: #6b7280; font-size: 14px;">IP Address:</td>
                                                                        <td align="right" style="color: #374151; font-size: 14px;">{client_ip}</td>
                                                                    </tr>
                                                                </table>
                                                            </td>
                                                        </tr>
                                                        <tr>
                                                            <td style="padding: 8px 0; border-bottom: 1px solid #e5e7eb;">
                                                                <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                                                    <tr>
                                                                        <td style="font-weight: 600; color: #6b7280; font-size: 14px;">Location:</td>
                                                                        <td align="right" style="color: #374151; font-size: 14px;">{location}</td>
                                                                    </tr>
                                                                </table>
                                                            </td>
                                                        </tr>
                                                        <tr>
                                                            <td style="padding: 8px 0;">
                                                                <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                                                    <tr>
                                                                        <td style="font-weight: 600; color: #6b7280; font-size: 14px;">Device:</td>
                                                                        <td align="right" style="color: #374151; font-size: 14px;">{device}</td>
                                                                    </tr>
                                                                </table>
                                                            </td>
                                                        </tr>
                                                    </table>
                                                </td>
                                            </tr>
                                        </table>

                                        <p style="margin: 24px 0 16px 0; font-weight: 600; color: #374151; font-size: 16px;">If this wasn't you:</p>
                                        <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                            <tr>
                                                <td style="padding: 4px 0;">
                                                    <p style="margin: 0; color: #374151; font-size: 15px;">• Change your password immediately</p>
                                                </td>
                                            </tr>
                                            <tr>
                                                <td style="padding: 4px 0;">
                                                    <p style="margin: 0; color: #374151; font-size: 15px;">• Review your account activity</p>
                                                </td>
                                            </tr>
                                            <tr>
                                                <td style="padding: 4px 0;">
                                                    <p style="margin: 0; color: #374151; font-size: 15px;">• Contact our support team</p>
                                                </td>
                                            </tr>
                                        </table>

                                        <!-- Action Buttons -->
                                        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="margin: 32px 0;">
                                            <tr>
                                                <td align="center">
                                                    <table border="0" cellpadding="0" cellspacing="0">
                                                        <tr>
                                                            <td style="padding: 0 8px 0 0;">
                                                                <a href="https://flow.axiestudio.se/settings/security" style="display: inline-block; background-color: #10b981; color: white; padding: 14px 28px; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 15px;">Secure My Account</a>
                                                            </td>
                                                            <td style="padding: 0 0 0 8px;">
                                                                <a href="https://flow.axiestudio.se/settings/password" style="display: inline-block; background-color: #ef4444; color: white; padding: 14px 28px; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 15px;">Change Password</a>
                                                            </td>
                                                        </tr>
                                                    </table>
                                                </td>
                                            </tr>
                                        </table>

                                        <!-- Security Tip -->
                                        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #f0f9ff; border-left: 4px solid #0ea5e9; border-radius: 4px; margin: 24px 0;">
                                            <tr>
                                                <td style="padding: 16px;">
                                                    <p style="margin: 0; color: #0c4a6e; font-size: 14px; line-height: 1.5;"><strong>💡 Security tip:</strong> Always log out from shared computers and use strong, unique passwords.</p>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="background-color: #f9fafb; padding: 32px 40px; text-align: center; border-top: 1px solid #e5e7eb; border-radius: 0 0 12px 12px;">
                            <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                <tr>
                                    <td align="center">
                                        <p style="margin: 0 0 8px 0; font-weight: 600; color: #374151; font-size: 16px;">AxieStudio</p>
                                        <p style="margin: 0; color: #6b7280; font-size: 14px;">Building the future of AI workflows</p>
                                        <p style="margin: 12px 0 0 0; color: #6b7280; font-size: 14px;">Visit us at <a href="https://flow.axiestudio.se" style="color: #3b82f6; text-decoration: none;">flow.axiestudio.se</a></p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
            """

            text_body = f"""
AxieStudio - New Sign-in Detected

Hello {username},

We detected a new sign-in to your AxieStudio account on {login_time}.

Sign-in Details:
- Account: {email}
- Time: {login_time}
- IP Address: {client_ip}
- Location: {location}
- Device: {device}

If this was you, you can safely ignore this email.

If this wasn't you:
1. Change your password immediately: https://flow.axiestudio.se/settings/password
2. Review your account activity: https://flow.axiestudio.se/settings/security
3. Contact our support team: {self.settings.SUPPORT_EMAIL}

Security tip: Always log out from shared computers and use strong, unique passwords.

---
AxieStudio - Building the future of AI workflows
Visit us at: https://flow.axiestudio.se
            """

            return await self._send_email(email, subject, text_body, html_body)

        except Exception as e:
            logger.error(f"Failed to send new login detection email to {email}: {e}")
            return False

    async def send_login_credentials_email(self, email: str, username: str, client_ip: str = "unknown") -> bool:
        """Send login credentials email with professional template."""
        try:
            subject = "Your AxieStudio Login Credentials"

            html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Your AxieStudio Login Credentials</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #1a202c;
            max-width: 600px;
            margin: 0 auto;
            padding: 0;
            background-color: #f7fafc;
        }}
        .email-container {{
            background-color: #ffffff;
            margin: 20px auto;
            border-radius: 12px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px 20px;
            text-align: center;
        }}

        .content {{
            padding: 40px;
        }}
        .credentials-box {{
            background-color: #f8fafc;
            border: 2px solid #e2e8f0;
            border-radius: 8px;
            padding: 24px;
            margin: 24px 0;
            text-align: center;
        }}
        .credential-item {{
            margin: 16px 0;
            padding: 12px;
            background-color: #ffffff;
            border-radius: 6px;
            border: 1px solid #e2e8f0;
        }}
        .credential-label {{
            font-weight: 600;
            color: #4a5568;
            font-size: 14px;
            margin-bottom: 4px;
        }}
        .credential-value {{
            font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
            font-size: 16px;
            color: #2d3748;
            font-weight: 600;
        }}
        .login-button {{
            display: inline-block;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 14px 32px;
            text-decoration: none;
            border-radius: 8px;
            font-weight: 600;
            margin: 20px 0;
        }}
        .footer {{
            background-color: #f7fafc;
            padding: 30px;
            text-align: center;
            color: #718096;
            font-size: 14px;
        }}
    </style>
</head>
<body>
    <div class="email-container">
        <div class="header">
            <img src="https://flow.axiestudio.se/logo192.png" alt="AxieStudio Logo" style="width: 48px; height: 48px; margin: 0 auto 16px auto; display: block; border-radius: 8px;">
            <h1>Your Login Credentials</h1>
            <p>Access your AxieStudio account</p>
        </div>

        <div class="content">
            <p>Hello <strong>{username}</strong>,</p>
            <p>As requested, here are your login credentials for AxieStudio:</p>

            <div class="credentials-box">
                <div class="credential-item">
                    <div class="credential-label">Username</div>
                    <div class="credential-value">{username}</div>
                </div>
                <div class="credential-item">
                    <div class="credential-label">Email</div>
                    <div class="credential-value">{email}</div>
                </div>
            </div>

            <div style="text-align: center; margin: 30px 0;">
                <a href="https://flow.axiestudio.se/login" class="login-button">
                    Login to AxieStudio
                </a>
            </div>

            <div style="background-color: #e6fffa; border-left: 4px solid #38b2ac; padding: 16px; margin: 24px 0; border-radius: 4px;">
                <p style="margin: 0; color: #234e52; font-weight: 500;"><strong>Security Note:</strong> Use your existing password to log in. If you've forgotten your password, you can change it in your account settings after logging in.</p>
            </div>

            <div style="background-color: #fee2e2; border-left: 4px solid #dc2626; padding: 16px; margin: 24px 0; border-radius: 4px;">
                <p style="margin: 0; color: #991b1b; font-weight: 500;"><strong>Security Notice:</strong> If you didn't request these credentials, please ignore this email.</p>
                <p style="margin: 8px 0 0 0; color: #991b1b; font-size: 12px;">Request originated from IP: {client_ip}</p>
            </div>
        </div>

        <div class="footer">
            <p><strong>AxieStudio</strong> - Building the future of AI workflows</p>
            <p>Visit us at <a href="https://axiestudio.se" style="color: #4299e1; text-decoration: none;">axiestudio.se</a></p>
        </div>
    </div>
</body>
</html>
            """

            text_body = f"""
AxieStudio - Your Login Credentials

Hello {username},

As requested, here are your login credentials for AxieStudio:

Username: {username}
Email: {email}

To log in, visit: https://flow.axiestudio.se/login

SECURITY NOTE: Use your existing password to log in. If you've forgotten your password, you can change it in your account settings after logging in.

Security Notice: If you didn't request these credentials, please ignore this email.
Request originated from IP: {client_ip}

---
AxieStudio - Building the future of AI workflows
Visit us at: https://axiestudio.se
            """

            return await self._send_email(email, subject, text_body, html_body)

        except Exception as e:
            logger.error(f"Failed to send login credentials email to {email}: {e}")
            return False

    async def send_trial_ending_email(self, email: str, username: str, days_left: int) -> bool:
        """Send trial ending notification email."""
        try:
            if days_left == 1:
                subject = "Your AxieStudio trial ends tomorrow"
                urgency_text = "Your trial ends tomorrow"
                urgency_color = "#e53e3e"
            elif days_left <= 3:
                subject = f"Your AxieStudio trial ends in {days_left} days"
                urgency_text = f"Your trial ends in {days_left} days"
                urgency_color = "#f6ad55"
            else:
                subject = f"Your AxieStudio trial ends in {days_left} days"
                urgency_text = f"Your trial ends in {days_left} days"
                urgency_color = "#4299e1"

            html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trial ending soon</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #1a202c;
            max-width: 600px;
            margin: 0 auto;
            padding: 0;
            background-color: #f7fafc;
        }}
        .email-container {{
            background: #ffffff;
            margin: 20px;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 40px 40px 30px;
            text-align: center;
        }}
        .logo {{
            background: rgba(255, 255, 255, 0.2);
            color: white;
            width: 60px;
            height: 60px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 24px;
            font-weight: bold;
            margin: 0 auto 20px;
        }}
        .header h1 {{
            color: white;
            margin: 0 0 8px 0;
            font-size: 28px;
            font-weight: 600;
        }}
        .header p {{
            color: rgba(255, 255, 255, 0.9);
            margin: 0;
            font-size: 16px;
        }}
        .content {{
            padding: 40px;
        }}
        .urgency-alert {{
            background: {urgency_color}15;
            border: 1px solid {urgency_color};
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
            text-align: center;
            color: {urgency_color};
            font-weight: 600;
            font-size: 18px;
        }}
        .subscribe-button {{
            display: inline-block;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 16px 32px;
            text-decoration: none;
            border-radius: 8px;
            font-weight: 600;
            font-size: 16px;
            margin: 20px 0;
        }}
        .features-list {{
            background: #f7fafc;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
        }}
        .feature-item {{
            padding: 8px 0;
            border-bottom: 1px solid #e2e8f0;
        }}
        .feature-item:last-child {{
            border-bottom: none;
        }}
        .footer {{
            background-color: #f7fafc;
            padding: 30px 40px;
            text-align: center;
            border-top: 1px solid #e2e8f0;
            color: #718096;
            font-size: 14px;
        }}
    </style>
</head>
<body>
    <div class="email-container">
        <div class="header">
            <img src="https://flow.axiestudio.se/logo192.png" alt="AxieStudio Logo" style="width: 48px; height: 48px; margin: 0 auto 16px auto; display: block; border-radius: 8px;" onerror="this.style.display='none'; this.nextElementSibling.style.display='block';">
            <div class="logo" style="display: none;">AX</div>
            <h1>Trial Ending Soon</h1>
            <p>Don't lose access to your AI workflows</p>
        </div>

        <div class="content">
            <p>Hello <strong>{username}</strong>,</p>

            <div class="urgency-alert">
                {urgency_text}
            </div>

            <p>Your AxieStudio trial has been amazing so far! To continue building powerful AI workflows without interruption, subscribe now and keep all your progress.</p>

            <div class="features-list">
                <div class="feature-item">✓ Unlimited AI workflow creation</div>
                <div class="feature-item">✓ Advanced automation features</div>
                <div class="feature-item">✓ Priority customer support</div>
                <div class="feature-item">✓ Export and backup capabilities</div>
                <div class="feature-item">✓ Team collaboration tools</div>
            </div>

            <div style="text-align: center; margin: 30px 0;">
                <a href="https://flow.axiestudio.se/pricing" class="subscribe-button">
                    Subscribe Now - Keep Building
                </a>
            </div>

            <p style="color: #718096; font-size: 14px;">
                Questions? Our support team is here to help at {self.settings.SUPPORT_EMAIL}
            </p>
        </div>

        <div class="footer">
            <p><strong>AxieStudio</strong> - Building the future of AI workflows</p>
            <p>Visit us at <a href="https://axiestudio.se" style="color: #4299e1; text-decoration: none;">axiestudio.se</a></p>
        </div>
    </div>
</body>
</html>
            """

            text_body = f"""
AxieStudio - Trial Ending Soon

Hello {username},

{urgency_text.upper()}

Your AxieStudio trial has been amazing so far! To continue building powerful AI workflows without interruption, subscribe now and keep all your progress.

What you'll keep with a subscription:
✓ Unlimited AI workflow creation
✓ Advanced automation features
✓ Priority customer support
✓ Export and backup capabilities
✓ Team collaboration tools

Subscribe now: https://flow.axiestudio.se/pricing

Questions? Our support team is here to help at {self.settings.SUPPORT_EMAIL}

---
AxieStudio - Building the future of AI workflows
Visit us at: https://axiestudio.se
            """

            return await self._send_email(email, subject, text_body, html_body)

        except Exception as e:
            logger.error(f"Failed to send trial ending email to {email}: {e}")
            return False

    async def send_subscription_cancelled_email(self, email: str, username: str, subscription_end_date: str) -> bool:
        """Send subscription cancellation confirmation email."""
        try:
            subject = "Your AxieStudio subscription has been cancelled"

            html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Subscription cancelled</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #1a202c;
            max-width: 600px;
            margin: 0 auto;
            padding: 0;
            background-color: #f7fafc;
        }}
        .email-container {{
            background: #ffffff;
            margin: 20px;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 40px 40px 30px;
            text-align: center;
        }}
        .logo {{
            background: rgba(255, 255, 255, 0.2);
            color: white;
            width: 60px;
            height: 60px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 24px;
            font-weight: bold;
            margin: 0 auto 20px;
        }}
        .header h1 {{
            color: white;
            margin: 0 0 8px 0;
            font-size: 28px;
            font-weight: 600;
        }}
        .header p {{
            color: rgba(255, 255, 255, 0.9);
            margin: 0;
            font-size: 16px;
        }}
        .content {{
            padding: 40px;
        }}
        .access-info {{
            background: #e6fffa;
            border: 1px solid #38a169;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
            text-align: center;
        }}
        .resubscribe-button {{
            display: inline-block;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 16px 32px;
            text-decoration: none;
            border-radius: 8px;
            font-weight: 600;
            font-size: 16px;
            margin: 20px 0;
        }}
        .footer {{
            background-color: #f7fafc;
            padding: 30px 40px;
            text-align: center;
            border-top: 1px solid #e2e8f0;
            color: #718096;
            font-size: 14px;
        }}
    </style>
</head>
<body>
    <div class="email-container">
        <div class="header">
            <img src="https://flow.axiestudio.se/logo192.png" alt="AxieStudio Logo" style="width: 48px; height: 48px; margin: 0 auto 16px auto; display: block; border-radius: 8px;" onerror="this.style.display='none'; this.nextElementSibling.style.display='block';">
            <div class="logo" style="display: none;">AX</div>
            <h1>Subscription Cancelled</h1>
            <p>We're sorry to see you go</p>
        </div>

        <div class="content">
            <p>Hello <strong>{username}</strong>,</p>
            <p>Your AxieStudio subscription has been successfully cancelled. We're sorry to see you go!</p>

            <div class="access-info">
                <strong>You still have access until {subscription_end_date}</strong><br>
                <span style="color: #4a5568; font-size: 14px;">Continue using all features until your current billing period ends</span>
            </div>

            <p><strong>What happens next:</strong></p>
            <ul>
                <li>Your account remains active until {subscription_end_date}</li>
                <li>All your workflows and data will be preserved</li>
                <li>You can resubscribe anytime to continue</li>
                <li>No further charges will be made</li>
            </ul>

            <p>Changed your mind? You can resubscribe anytime:</p>

            <div style="text-align: center; margin: 30px 0;">
                <a href="https://flow.axiestudio.se/pricing" class="resubscribe-button">
                    Resubscribe Now
                </a>
            </div>

            <p style="color: #718096; font-size: 14px;">
                We'd love to hear your feedback at {self.settings.SUPPORT_EMAIL}
            </p>
        </div>

        <div class="footer">
            <p><strong>AxieStudio</strong> - Building the future of AI workflows</p>
            <p>Visit us at <a href="https://axiestudio.se" style="color: #4299e1; text-decoration: none;">axiestudio.se</a></p>
        </div>
    </div>
</body>
</html>
            """

            text_body = f"""
AxieStudio - Subscription Cancelled

Hello {username},

Your AxieStudio subscription has been successfully cancelled. We're sorry to see you go!

IMPORTANT: You still have access until {subscription_end_date}

What happens next:
- Your account remains active until {subscription_end_date}
- All your workflows and data will be preserved
- You can resubscribe anytime to continue
- No further charges will be made

Changed your mind? Resubscribe anytime: https://flow.axiestudio.se/pricing

We'd love to hear your feedback at {self.settings.SUPPORT_EMAIL}

---
AxieStudio - Building the future of AI workflows
Visit us at: https://axiestudio.se
            """

            return await self._send_email(email, subject, text_body, html_body)

        except Exception as e:
            logger.error(f"Failed to send subscription cancelled email to {email}: {e}")
            return False

    async def send_subscription_reactivated_email(self, email: str, username: str, subscription_end_date: str) -> bool:
        """Send subscription reactivation confirmation email."""
        try:
            subject = "Your AxieStudio subscription has been reactivated"

            html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Subscription reactivated</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f8f9fa;
        }}
        .container {{
            background-color: white;
            border-radius: 8px;
            padding: 40px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 2px solid #e9ecef;
        }}
        .logo {{
            font-size: 24px;
            font-weight: bold;
            color: #2563eb;
            margin-bottom: 10px;
        }}
        .title {{
            font-size: 28px;
            font-weight: bold;
            color: #1a1a1a;
            margin: 0;
        }}
        .content {{
            margin-bottom: 30px;
        }}
        .highlight {{
            background-color: #dbeafe;
            padding: 20px;
            border-radius: 6px;
            border-left: 4px solid #2563eb;
            margin: 20px 0;
        }}
        .button {{
            display: inline-block;
            background-color: #2563eb;
            color: white;
            padding: 12px 24px;
            text-decoration: none;
            border-radius: 6px;
            font-weight: 500;
            margin: 20px 0;
        }}
        .footer {{
            text-align: center;
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #e9ecef;
            color: #6b7280;
            font-size: 14px;
        }}
        .success-icon {{
            font-size: 48px;
            color: #10b981;
            text-align: center;
            margin-bottom: 20px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <img src="https://flow.axiestudio.se/logo192.png" alt="AxieStudio Logo" style="width: 48px; height: 48px; margin: 0 auto 16px auto; display: block; border-radius: 8px;" onerror="this.style.display='none'; this.nextElementSibling.style.display='block';">
            <div class="logo" style="display: none;">AxieStudio</div>
            <h1 class="title">Subscription Reactivated! 🎉</h1>
        </div>

        <div class="success-icon">✅</div>

        <div class="content">
            <p>Hi {username},</p>

            <p>Great news! Your AxieStudio subscription has been successfully reactivated.</p>

            <div class="highlight">
                <strong>Your subscription is now active again!</strong><br>
                You now have full access to all Pro features until {subscription_end_date}.
            </div>

            <p>You can now enjoy:</p>
            <ul>
                <li>Unlimited AI conversations</li>
                <li>Advanced flow creation tools</li>
                <li>Priority support</li>
                <li>All premium features</li>
            </ul>

            <div style="text-align: center;">
                <a href="https://flow.axiestudio.se/dashboard" class="button">Access Your Dashboard</a>
            </div>

            <p>If you have any questions or need assistance, our support team is here to help.</p>

            <p>Welcome back!</p>
            <p>The AxieStudio Team</p>
        </div>

        <div class="footer">
            <p>This email was sent to {email}</p>
            <p>AxieStudio - AI-Powered Flow Creation Platform</p>
        </div>
    </div>
</body>
</html>
"""

            # Send the email
            success = await self._send_email(
                to_email=email,
                subject=subject,
                html_content=html_body
            )

            if success:
                logger.info(f"✅ Sent subscription reactivation email to {email}")
                return True
            else:
                logger.error(f"❌ Failed to send subscription reactivation email to {email}")
                return False

        except Exception as e:
            logger.error(f"Failed to send subscription reactivation email to {email}: {e}")
            return False

    async def send_subscription_welcome_email(self, email: str, username: str, plan_name: str = "Pro") -> bool:
        """Send subscription welcome email."""
        try:
            subject = f"Welcome to AxieStudio {plan_name}! Your subscription is active"

            html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Welcome to AxieStudio Pro</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #1a202c;
            max-width: 600px;
            margin: 0 auto;
            padding: 0;
            background-color: #f7fafc;
        }}
        .email-container {{
            background: #ffffff;
            margin: 20px;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
        }}
        .header {{
            background: linear-gradient(135deg, #38a169 0%, #2f855a 100%);
            padding: 40px 40px 30px;
            text-align: center;
        }}
        .logo {{
            background: rgba(255, 255, 255, 0.2);
            color: white;
            width: 60px;
            height: 60px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 24px;
            font-weight: bold;
            margin: 0 auto 20px;
        }}
        .header h1 {{
            color: white;
            margin: 0 0 8px 0;
            font-size: 28px;
            font-weight: 600;
        }}
        .header p {{
            color: rgba(255, 255, 255, 0.9);
            margin: 0;
            font-size: 16px;
        }}
        .content {{
            padding: 40px;
        }}
        .welcome-badge {{
            background: linear-gradient(135deg, #38a169 0%, #2f855a 100%);
            color: white;
            padding: 12px 24px;
            border-radius: 25px;
            display: inline-block;
            font-weight: 600;
            margin: 20px 0;
        }}
        .features-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
            margin: 20px 0;
        }}
        .feature-card {{
            background: #f7fafc;
            border-radius: 8px;
            padding: 15px;
            text-align: center;
        }}
        .get-started-button {{
            display: inline-block;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 16px 32px;
            text-decoration: none;
            border-radius: 8px;
            font-weight: 600;
            font-size: 16px;
            margin: 20px 0;
        }}
        .next-steps {{
            background: #e6fffa;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
        }}
        .step-item {{
            padding: 8px 0;
            border-bottom: 1px solid #b2f5ea;
        }}
        .step-item:last-child {{
            border-bottom: none;
        }}
        .footer {{
            background-color: #f7fafc;
            padding: 30px 40px;
            text-align: center;
            border-top: 1px solid #e2e8f0;
            color: #718096;
            font-size: 14px;
        }}
    </style>
</head>
<body>
    <div class="email-container">
        <div class="header">
            <img src="https://flow.axiestudio.se/logo192.png" alt="AxieStudio Logo" style="width: 48px; height: 48px; margin: 0 auto 16px auto; display: block; border-radius: 8px;" onerror="this.style.display='none'; this.nextElementSibling.style.display='block';">
            <div class="logo" style="display: none;">AX</div>
            <h1>Welcome to {plan_name}!</h1>
            <p>Your subscription is now active</p>
        </div>

        <div class="content">
            <p>Hello <strong>{username}</strong>,</p>

            <div style="text-align: center;">
                <div class="welcome-badge">🎉 AxieStudio {plan_name} Activated</div>
            </div>

            <p>Congratulations! Your AxieStudio {plan_name} subscription is now active. You now have access to all premium features and can build unlimited AI workflows.</p>

            <div class="features-grid">
                <div class="feature-card">
                    <strong>Unlimited Workflows</strong><br>
                    <span style="color: #718096; font-size: 14px;">Create as many AI workflows as you need</span>
                </div>
                <div class="feature-card">
                    <strong>Advanced Features</strong><br>
                    <span style="color: #718096; font-size: 14px;">Access all premium automation tools</span>
                </div>
                <div class="feature-card">
                    <strong>Priority Support</strong><br>
                    <span style="color: #718096; font-size: 14px;">Get help when you need it most</span>
                </div>
                <div class="feature-card">
                    <strong>Export & Backup</strong><br>
                    <span style="color: #718096; font-size: 14px;">Keep your work safe and portable</span>
                </div>
            </div>

            <div class="next-steps">
                <h3 style="margin-top: 0; color: #2f855a;">Next Steps:</h3>
                <div class="step-item">1. Explore the advanced workflow builder</div>
                <div class="step-item">2. Try the new automation features</div>
                <div class="step-item">3. Set up your team collaboration</div>
                <div class="step-item">4. Join our community for tips and tricks</div>
            </div>

            <div style="text-align: center; margin: 30px 0;">
                <a href="https://flow.axiestudio.se/dashboard" class="get-started-button">
                    Start Building Now
                </a>
            </div>

            <p style="color: #718096; font-size: 14px;">
                Need help getting started? Our support team is ready to assist at {self.settings.SUPPORT_EMAIL}
            </p>
        </div>

        <div class="footer">
            <p><strong>AxieStudio</strong> - Building the future of AI workflows</p>
            <p>Visit us at <a href="https://axiestudio.se" style="color: #4299e1; text-decoration: none;">axiestudio.se</a></p>
        </div>
    </div>
</body>
</html>
            """

            text_body = f"""
AxieStudio - Welcome to {plan_name}!

Hello {username},

🎉 Congratulations! Your AxieStudio {plan_name} subscription is now active.

You now have access to:
✓ Unlimited AI workflows
✓ Advanced automation features
✓ Priority customer support
✓ Export and backup capabilities
✓ Team collaboration tools

Next Steps:
1. Explore the advanced workflow builder
2. Try the new automation features
3. Set up your team collaboration
4. Join our community for tips and tricks

Start building now: https://flow.axiestudio.se/dashboard

Need help getting started? Our support team is ready to assist at {self.settings.SUPPORT_EMAIL}

---
AxieStudio - Building the future of AI workflows
Visit us at: https://axiestudio.se
            """

            return await self._send_email(email, subject, text_body, html_body)

        except Exception as e:
            logger.error(f"Failed to send subscription welcome email to {email}: {e}")
            return False

    async def _send_email(self, to_email: str, subject: str, text_body: str, html_body: str) -> bool:
        """Send email using dual method: Resend SDK (primary) + SMTP (fallback)."""

        # Try Resend SDK first (if available)
        if self.preferred_method == EmailMethod.SDK and RESEND_SDK_AVAILABLE:
            logger.debug(f"🚀 Attempting to send email via Resend SDK to: {to_email}")
            success = await self._send_email_via_sdk(to_email, subject, text_body, html_body)
            if success:
                logger.info(f"✅ Email sent successfully via Resend SDK to: {to_email}")
                return True
            else:
                logger.warning(f"⚠️ Resend SDK failed, falling back to SMTP for: {to_email}")

        # Fallback to SMTP or primary SMTP method
        logger.debug(f"📧 Attempting to send email via SMTP to: {to_email}")
        success = await self._send_email_via_smtp(to_email, subject, text_body, html_body)
        if success:
            logger.info(f"✅ Email sent successfully via SMTP to: {to_email}")
            return True
        else:
            logger.error(f"❌ Both email methods failed for: {to_email}")
            return False

    async def _send_email_via_sdk(self, to_email: str, subject: str, text_body: str, html_body: str) -> bool:
        """Send email using Resend Python SDK."""
        if not RESEND_SDK_AVAILABLE:
            logger.error("Resend SDK not available")
            return False

        try:
            # Configure Resend API key
            resend.api_key = self.settings.SMTP_PASSWORD  # Resend API key

            # Prepare email parameters
            params = {
                "from": f"{self.settings.FROM_NAME} <{self.settings.FROM_EMAIL}>",
                "to": [to_email],
                "subject": subject,
                "html": html_body,
                "text": text_body
            }

            logger.debug(f"📤 Sending via Resend SDK with params: {params['from']} -> {params['to']}")

            # Send email via Resend SDK (synchronous call)
            import asyncio
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, lambda: resend.Emails.send(params))

            # Handle both dict and object responses from Resend SDK
            if response:
                # Extract email ID from response (dict or object)
                email_id = None
                if isinstance(response, dict) and 'id' in response:
                    email_id = response['id']
                elif hasattr(response, 'id'):
                    email_id = response.id

                if email_id:
                    logger.info(f"✅ Resend SDK success - Email ID: {email_id}")
                    return True
                else:
                    logger.error(f"❌ Resend SDK failed - No ID in response: {response}")
                    return False
            else:
                logger.error(f"❌ Resend SDK failed - Empty response")
                return False

        except Exception as e:
            logger.error(f"❌ Resend SDK error: {e}")
            return False

    async def _send_email_via_smtp(self, to_email: str, subject: str, text_body: str, html_body: str) -> bool:
        """Send email using SMTP with enterprise-level error handling and security."""
        try:
            # Debug logging for email configuration
            logger.info(f"EMAIL DEBUG - Attempting to send email to: {to_email}")
            logger.info(f"EMAIL DEBUG - SMTP Host: {self.settings.SMTP_HOST}")
            logger.info(f"EMAIL DEBUG - SMTP Port: {self.settings.SMTP_PORT}")
            logger.info(f"EMAIL DEBUG - SMTP User: {self.settings.SMTP_USER}")
            logger.info(f"EMAIL DEBUG - From Email: {self.settings.FROM_EMAIL}")
            logger.info(f"EMAIL DEBUG - Email Enabled: {getattr(self.settings, 'EMAIL_ENABLED', True)}")

            # Check if email is disabled
            if not getattr(self.settings, 'EMAIL_ENABLED', True):
                logger.warning("Email sending is disabled (EMAIL_ENABLED=False)")
                return False

            # Validate email settings
            if not self.settings.SMTP_USER or not self.settings.SMTP_PASSWORD:
                logger.error("SMTP credentials not configured. Please set AXIESTUDIO_EMAIL_SMTP_USER and AXIESTUDIO_EMAIL_SMTP_PASSWORD")
                return False

            if not self.settings.FROM_EMAIL or "@" not in self.settings.FROM_EMAIL:
                logger.error("Invalid FROM_EMAIL configuration")
                return False

            # Validate Resend configuration specifically
            if self.settings.SMTP_HOST == "smtp.resend.com":
                if self.settings.SMTP_USER != "resend":
                    logger.error(f"For Resend SMTP, SMTP_USER must be 'resend', got: {self.settings.SMTP_USER}")
                    return False
                if not self.settings.SMTP_PASSWORD.startswith("re_"):
                    logger.error("For Resend SMTP, SMTP_PASSWORD must be a Resend API key (starts with 're_')")
                    return False

            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.settings.FROM_EMAIL
            msg['To'] = to_email

            # Create text and HTML parts
            text_part = MIMEText(text_body, 'plain', 'utf-8')
            html_part = MIMEText(html_body, 'html', 'utf-8')

            # Add parts to message
            msg.attach(text_part)
            msg.attach(html_part)

            # Send email with detailed debugging
            logger.info(f"SMTP CONFIG - Host: {self.settings.SMTP_HOST}:{self.settings.SMTP_PORT}")
            logger.info(f"SMTP CONFIG - User: {self.settings.SMTP_USER}")
            logger.info(f"SMTP CONFIG - From: {self.settings.FROM_EMAIL}")
            logger.info(f"SMTP CONFIG - To: {to_email}")
            logger.info(f"EMAIL DEBUG - Connecting to SMTP server...")
            with smtplib.SMTP(self.settings.SMTP_HOST, self.settings.SMTP_PORT) as server:
                logger.info(f"EMAIL DEBUG - Connection established successfully")
                logger.info(f"EMAIL DEBUG - Starting TLS...")
                server.starttls()
                logger.info(f"EMAIL DEBUG - TLS started successfully")
                logger.info(f"EMAIL DEBUG - Logging in with user: {self.settings.SMTP_USER}")
                server.login(self.settings.SMTP_USER, self.settings.SMTP_PASSWORD)
                logger.info(f"EMAIL DEBUG - Authentication successful")
                logger.info(f"EMAIL DEBUG - Sending message...")
                server.send_message(msg)
                logger.info(f"EMAIL DEBUG - Message sent to SMTP server successfully")

            logger.info(f"Email sent successfully to {to_email}")
            return True

        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"SMTP authentication failed: {e}")
            logger.error(f"SMTP AUTH DEBUG - Host: {self.settings.SMTP_HOST}, User: {self.settings.SMTP_USER}")
            logger.error(f"SMTP AUTH DEBUG - Password length: {len(self.settings.SMTP_PASSWORD) if self.settings.SMTP_PASSWORD else 0}")
            return False

        except smtplib.SMTPRecipientsRefused as e:
            logger.error(f"SMTP recipients refused: {e}")
            return False

        except smtplib.SMTPException as e:
            logger.error(f"SMTP error occurred: {e}")
            return False

        except ConnectionError as e:
            logger.error(f"Connection error to SMTP server: {e}")
            return False

        except TimeoutError as e:
            logger.error(f"Timeout connecting to SMTP server: {e}")
            return False

        except Exception as e:
            logger.exception(f"Unexpected error sending email to {to_email}: {e}")
            logger.error(f"ERROR DEBUG - SMTP Config: {self.settings.SMTP_HOST}:{self.settings.SMTP_PORT}")
            logger.error(f"ERROR DEBUG - From: {self.settings.FROM_EMAIL}, To: {to_email}")
            return False


# Global email service instance
email_service = EmailService()
