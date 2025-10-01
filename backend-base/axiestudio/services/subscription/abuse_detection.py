"""Subscription abuse detection service for preventing subscription manipulation."""

import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

from axiestudio.logging import logger
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from axiestudio.services.database.models.user.model import User


class SubscriptionAbuseDetectionService:
    """Service for detecting and preventing subscription abuse patterns."""
    
    def __init__(self):
        self.subscription_cooldown_days = 7  # Prevent rapid subscription cycles
        self.max_cancellations_per_month = 3  # Max cancellations per month
        self.max_trials_per_payment_method = 2  # Max trials per payment method
    
    async def check_subscription_abuse(
        self,
        session: AsyncSession,
        user: User,
        action: str,  # "create", "cancel", "reactivate"
        payment_method_fingerprint: Optional[str] = None
    ) -> Dict[str, Any]:
        """Check if subscription action appears to be abuse."""
        abuse_indicators = []
        risk_score = 0
        
        now = datetime.now(timezone.utc)
        
        # Check 1: Rapid subscription cycling
        if action == "create":
            # Check for recent subscription activity
            recent_cutoff = now - timedelta(days=self.subscription_cooldown_days)
            
            # Look for users with same email/IP who recently had subscriptions
            recent_subscription_users = await self._get_recent_subscription_users(
                session, user, recent_cutoff
            )
            
            if recent_subscription_users:
                abuse_indicators.append(f"recent_subscription_activity_{len(recent_subscription_users)}_users")
                risk_score += 40 * len(recent_subscription_users)
        
        # Check 2: Excessive cancellation pattern
        if action == "cancel":
            cancellation_count = await self._get_user_cancellation_count(session, user, days=30)
            
            if cancellation_count >= self.max_cancellations_per_month:
                abuse_indicators.append(f"excessive_cancellations_{cancellation_count}_in_30_days")
                risk_score += 60
        
        # Check 3: Payment method abuse (if available)
        if payment_method_fingerprint and action == "create":
            payment_method_usage = await self._check_payment_method_usage(
                session, payment_method_fingerprint
            )
            
            if payment_method_usage["trial_count"] > self.max_trials_per_payment_method:
                abuse_indicators.append(f"payment_method_overuse_{payment_method_usage['trial_count']}_trials")
                risk_score += 50
        
        # Check 4: Rapid cancel-reactivate cycles
        if action in ["cancel", "reactivate"]:
            rapid_cycles = await self._detect_rapid_cycles(session, user)
            
            if rapid_cycles > 2:
                abuse_indicators.append(f"rapid_cancel_reactivate_cycles_{rapid_cycles}")
                risk_score += 30 * rapid_cycles
        
        # Check 5: Trial-to-subscription-to-cancel pattern
        if action == "cancel":
            suspicious_pattern = await self._detect_trial_subscription_cancel_pattern(session, user)
            
            if suspicious_pattern:
                abuse_indicators.append("trial_subscription_cancel_pattern")
                risk_score += 70
        
        # Determine action based on risk score
        if risk_score >= 150:
            action_result = "block"
            message = "Subscription action blocked due to abuse detection. Please contact support."
        elif risk_score >= 100:
            action_result = "flag"
            message = "Subscription action flagged for manual review."
        elif risk_score >= 50:
            action_result = "warn"
            message = "Subscription activity appears suspicious - monitoring enabled."
        else:
            action_result = "allow"
            message = "Subscription action appears legitimate."
        
        result = {
            "action": action_result,
            "risk_score": risk_score,
            "abuse_indicators": abuse_indicators,
            "message": message,
            "details": {
                "user_id": str(user.id),
                "action_type": action,
                "timestamp": now.isoformat(),
                "cooldown_days": self.subscription_cooldown_days
            }
        }
        
        logger.info(f"Subscription abuse check for user {user.username}: {result}")
        return result
    
    async def _get_recent_subscription_users(
        self, 
        session: AsyncSession, 
        user: User, 
        cutoff_date: datetime
    ) -> list:
        """Get users with recent subscription activity from same IP/email domain."""
        # Check for same IP
        if user.signup_ip:
            ip_stmt = select(User).where(
                User.signup_ip == user.signup_ip,
                User.subscription_id.isnot(None),
                User.updated_at > cutoff_date,
                User.id != user.id
            )
            ip_users = (await session.exec(ip_stmt)).all()
            return ip_users
        
        return []
    
    async def _get_user_cancellation_count(
        self, 
        session: AsyncSession, 
        user: User, 
        days: int
    ) -> int:
        """Count user's subscription cancellations in the last N days."""
        # This would require a subscription history table in a real implementation
        # For now, we'll use a simplified check based on current status
        if user.subscription_status == "canceled":
            return 1
        return 0
    
    async def _check_payment_method_usage(
        self, 
        session: AsyncSession, 
        payment_method_fingerprint: str
    ) -> Dict[str, int]:
        """Check how many times a payment method has been used."""
        # This would require storing payment method fingerprints
        # For now, return default values
        return {
            "trial_count": 0,
            "subscription_count": 0,
            "cancellation_count": 0
        }
    
    async def _detect_rapid_cycles(self, session: AsyncSession, user: User) -> int:
        """Detect rapid cancel-reactivate cycles."""
        # This would require subscription history tracking
        # For now, return 0 (no cycles detected)
        return 0
    
    async def _detect_trial_subscription_cancel_pattern(
        self, 
        session: AsyncSession, 
        user: User
    ) -> bool:
        """Detect trial -> subscription -> immediate cancel pattern."""
        # Check if user:
        # 1. Recently had trial
        # 2. Subscribed
        # 3. Is now canceling quickly
        
        if not user.trial_start or not user.subscription_start:
            return False
        
        # If subscription started soon after trial and user is canceling quickly
        trial_to_subscription_gap = (user.subscription_start - user.trial_start).days
        subscription_duration = (datetime.now(timezone.utc) - user.subscription_start).days
        
        # Suspicious if: trial -> subscription within 1 day, canceling within 3 days
        if trial_to_subscription_gap <= 1 and subscription_duration <= 3:
            return True
        
        return False
    
    async def log_subscription_action(
        self,
        session: AsyncSession,
        user: User,
        action: str,
        risk_score: int,
        abuse_indicators: list
    ):
        """Log subscription action for monitoring and analysis."""
        logger.info(
            f"Subscription action logged: user={user.username}, action={action}, "
            f"risk_score={risk_score}, indicators={abuse_indicators}"
        )


# Global instance
subscription_abuse_detection = SubscriptionAbuseDetectionService()
