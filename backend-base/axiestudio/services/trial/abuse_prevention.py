"""Trial abuse prevention service for detecting and preventing multiple trial signups."""

import hashlib
import ipaddress
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import Request
from axiestudio.logging import logger
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from axiestudio.services.database.models.user.model import User


class TrialAbusePreventionService:
    """Service for preventing trial abuse through multiple signups."""
    
    def __init__(self):
        self.trial_cooldown_days = 30  # Prevent new trials from same IP/device for 30 days
    
    def extract_client_ip(self, request: Request) -> str:
        """Extract the real client IP address from request."""
        # Check for X-Forwarded-For header (common when behind proxies/load balancers)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # The client IP is the first one in the list
            client_ip = forwarded_for.split(",")[0].strip()
        elif request.headers.get("X-Real-IP"):
            # Alternative header used by some proxies
            client_ip = request.headers.get("X-Real-IP")
        elif hasattr(request, 'client') and request.client:
            # Direct connection IP
            client_ip = request.client.host
        else:
            # Fallback
            client_ip = "unknown"
        
        # Normalize IP address
        try:
            # This will validate and normalize the IP
            normalized_ip = str(ipaddress.ip_address(client_ip))
            return normalized_ip
        except ValueError:
            # If IP is invalid, return as-is but log warning
            logger.warning(f"Invalid IP address detected: {client_ip}")
            return client_ip
    
    def generate_device_fingerprint(self, request: Request) -> str:
        """Generate a device fingerprint from request headers."""
        # Collect identifying headers
        fingerprint_data = []
        
        # User-Agent is the most identifying header
        user_agent = request.headers.get("User-Agent", "")
        fingerprint_data.append(f"ua:{user_agent}")
        
        # Accept headers can help identify browser/device
        accept = request.headers.get("Accept", "")
        fingerprint_data.append(f"accept:{accept}")
        
        accept_language = request.headers.get("Accept-Language", "")
        fingerprint_data.append(f"lang:{accept_language}")
        
        accept_encoding = request.headers.get("Accept-Encoding", "")
        fingerprint_data.append(f"encoding:{accept_encoding}")
        
        # Screen resolution and other client hints (if available)
        sec_ch_ua = request.headers.get("Sec-CH-UA", "")
        fingerprint_data.append(f"ch_ua:{sec_ch_ua}")
        
        sec_ch_ua_platform = request.headers.get("Sec-CH-UA-Platform", "")
        fingerprint_data.append(f"ch_platform:{sec_ch_ua_platform}")
        
        # Combine all data and create hash
        combined_data = "|".join(fingerprint_data)
        fingerprint_hash = hashlib.sha256(combined_data.encode()).hexdigest()[:16]  # First 16 chars
        
        logger.debug(f"Generated device fingerprint: {fingerprint_hash}")
        return fingerprint_hash
    
    def _is_disposable_email(self, email: str) -> bool:
        """Check if email is from a known disposable email service."""
        disposable_domains = {
            "10minutemail.com", "guerrillamail.com", "mailinator.com",
            "tempmail.org", "throwaway.email", "temp-mail.org",
            "yopmail.com", "maildrop.cc", "sharklasers.com"
        }
        domain = email.split("@")[-1].lower()
        return domain in disposable_domains

    def _normalize_email(self, email: str) -> str:
        """Normalize email to detect aliases and variations."""
        email = email.lower().strip()
        local, domain = email.split("@")

        # Remove + aliases (user+alias@domain.com -> user@domain.com)
        if "+" in local:
            local = local.split("+")[0]

        # Handle Gmail dot variations (user.name@gmail.com -> username@gmail.com)
        if domain in ["gmail.com", "googlemail.com"]:
            local = local.replace(".", "")
            domain = "gmail.com"  # Normalize googlemail to gmail

        return f"{local}@{domain}"

    def _is_suspicious_ip(self, ip: str) -> bool:
        """Check if IP address appears suspicious."""
        try:
            ip_obj = ipaddress.ip_address(ip)

            # Check for private/local IPs (except localhost which is handled separately)
            if ip_obj.is_private and ip not in ["127.0.0.1", "::1"]:
                return True

            # Check for known VPN/proxy ranges (simplified check)
            # In production, you'd use a more comprehensive IP reputation service
            suspicious_ranges = [
                "10.0.0.0/8",      # Private range often used by VPNs
                "172.16.0.0/12",   # Private range
                "192.168.0.0/16",  # Private range
            ]

            for range_str in suspicious_ranges:
                if ip_obj in ipaddress.ip_network(range_str):
                    return True

            return False
        except ValueError:
            # Invalid IP format is suspicious
            return True

    async def check_trial_abuse(
        self,
        session: AsyncSession,
        email: Optional[str],
        signup_ip: str,
        device_fingerprint: str
    ) -> dict:
        """Check if this signup attempt appears to be trial abuse."""
        abuse_indicators = []
        risk_score = 0

        # Check 1: Email validation and normalization
        if email:
            # Check for disposable email
            if self._is_disposable_email(email):
                abuse_indicators.append("disposable_email")
                risk_score += 75  # High risk - disposable email

            # Normalize email to catch aliases
            normalized_email = self._normalize_email(email)

            # Check if normalized email already exists
            email_stmt = select(User).where(User.email == email)
            existing_email_user = (await session.exec(email_stmt)).first()
            if existing_email_user:
                abuse_indicators.append("email_already_used")
                risk_score += 100  # High risk - email already exists

            # Check for normalized email variations
            if normalized_email != email:
                normalized_stmt = select(User).where(User.email.like(f"{normalized_email.split('@')[0]}%@{normalized_email.split('@')[1]}"))
                similar_emails = (await session.exec(normalized_stmt)).all()
                if similar_emails:
                    abuse_indicators.append(f"email_variation_detected_{len(similar_emails)}_similar")
                    risk_score += 50  # Medium risk - email variations
        
        # Check 2: IP address recently used for trial
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=self.trial_cooldown_days)
        ip_stmt = select(User).where(
            User.signup_ip == signup_ip,
            User.create_at > cutoff_date
        )
        recent_ip_users = (await session.exec(ip_stmt)).all()
        
        if recent_ip_users:
            abuse_indicators.append(f"ip_recently_used_{len(recent_ip_users)}_times")
            risk_score += 50 * len(recent_ip_users)  # Escalating risk
        
        # Check 3: Device fingerprint recently used
        device_stmt = select(User).where(
            User.device_fingerprint == device_fingerprint,
            User.create_at > cutoff_date
        )
        recent_device_users = (await session.exec(device_stmt)).all()
        
        if recent_device_users:
            abuse_indicators.append(f"device_recently_used_{len(recent_device_users)}_times")
            risk_score += 30 * len(recent_device_users)  # Medium risk
        
        # Check 4: Suspicious patterns
        if signup_ip in ["127.0.0.1", "localhost", "::1"]:
            abuse_indicators.append("localhost_signup")
            risk_score += 5  # Very low risk - development

        # Check 5: Rapid signup patterns (multiple signups in short time)
        recent_signups_stmt = select(User).where(
            User.create_at > cutoff_date
        )
        recent_signups = (await session.exec(recent_signups_stmt)).all()

        # If too many recent signups overall, increase risk
        if len(recent_signups) > 50:  # More than 50 signups in 30 days
            abuse_indicators.append("high_signup_volume")
            risk_score += 20

        # Check 6: Suspicious IP patterns
        if self._is_suspicious_ip(signup_ip):
            abuse_indicators.append("suspicious_ip")
            risk_score += 30

        # Determine action based on risk score with more nuanced thresholds
        if risk_score >= 150:
            action = "block"
            message = "Account creation blocked due to high abuse risk. Please contact support."
        elif risk_score >= 100:
            action = "block"
            message = "Account creation temporarily restricted. Please try again later or contact support."
        elif risk_score >= 75:
            action = "warn"
            message = "High risk signup detected - account created but flagged for monitoring."
        elif risk_score >= 50:
            action = "warn"
            message = "Medium risk signup detected - monitoring required."
        else:
            action = "allow"
            message = "Signup appears legitimate."
        
        result = {
            "action": action,
            "risk_score": risk_score,
            "abuse_indicators": abuse_indicators,
            "message": message,
            "details": {
                "email_check": bool(email and existing_email_user),
                "ip_usage_count": len(recent_ip_users),
                "device_usage_count": len(recent_device_users),
                "cooldown_days": self.trial_cooldown_days
            }
        }
        
        logger.info(f"Trial abuse check result: {result}")
        return result
    
    async def log_signup_attempt(
        self, 
        session: AsyncSession, 
        email: Optional[str], 
        signup_ip: str, 
        device_fingerprint: str, 
        success: bool,
        risk_score: int
    ):
        """Log signup attempt for monitoring and analysis."""
        # This could be extended to log to a separate table for analytics
        logger.info(
            f"Signup attempt logged: email={email}, ip={signup_ip}, "
            f"fingerprint={device_fingerprint}, success={success}, risk_score={risk_score}"
        )


# Global instance
trial_abuse_prevention = TrialAbusePreventionService()
