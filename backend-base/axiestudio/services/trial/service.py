"""Trial management service for handling user trials and cleanup."""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import List

from axiestudio.logging import logger
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from axiestudio.services.database.models.user.model import User
from axiestudio.services.database.models.user.crud import get_user_by_id
try:
    from axiestudio.services.deps import get_db_service
except ImportError:
    # Fallback for when deps are not available
    get_db_service = None


class TrialService:
    """Service for managing user trials and cleanup."""
    
    def __init__(self):
        self.trial_duration_days = 7
    
    async def check_trial_status(self, user: User) -> dict:
        """Check if user's trial is active, expired, or if they have a subscription."""
        now = datetime.now(timezone.utc)

        # Superusers bypass all subscription checks
        if user.is_superuser:
            return {
                "status": "admin",
                "trial_expired": False,
                "days_left": 0,
                "should_cleanup": False
            }

        # If user has active subscription, they're good
        if user.subscription_status == "active":
            logger.info(f"✅ User {user.username} has active subscription - granting access")
            return {
                "status": "subscribed",
                "trial_expired": False,
                "days_left": 0,
                "should_cleanup": False
            }

        # CRITICAL FIX: Graceful degradation during Stripe outages
        # If user has subscription_id but we can't verify with Stripe, give benefit of doubt
        if user.subscription_id and user.subscription_status in ["active", "canceled"]:
            # Check if subscription_end is in the future (user paid for access)
            if user.subscription_end:
                subscription_end = user.subscription_end
                if subscription_end.tzinfo is None:
                    subscription_end = subscription_end.replace(tzinfo=timezone.utc)

                if now < subscription_end:
                    # User has paid subscription that hasn't expired - allow access even if Stripe is down
                    remaining_seconds = (subscription_end - now).total_seconds()
                    days_left = max(0, int(remaining_seconds / 86400))
                    return {
                        "status": "subscription_grace_period",
                        "trial_expired": False,
                        "days_left": days_left,
                        "should_cleanup": False,
                        "subscription_end": subscription_end,
                        "grace_period": True  # Indicates this is fallback during service issues
                    }

        # FIXED: Handle canceled subscriptions that are still valid until subscription_end
        if user.subscription_status == "canceled" and user.subscription_end:
            # Ensure timezone consistency
            subscription_end = user.subscription_end
            if subscription_end.tzinfo is None:
                subscription_end = subscription_end.replace(tzinfo=timezone.utc)

            # CRITICAL FIX: Only allow canceled access if user has a subscription_id
            # This prevents access after subscription has actually been deleted
            if user.subscription_id and now < subscription_end:
                remaining_seconds = (subscription_end - now).total_seconds()
                days_left = max(0, int(remaining_seconds / 86400))
                return {
                    "status": "canceled_but_active",
                    "trial_expired": False,
                    "days_left": days_left,
                    "should_cleanup": False,
                    "subscription_end": subscription_end
                }
            elif not user.subscription_id:
                # Subscription was actually deleted - no more access
                logger.info(f"User {user.username} has canceled status but no subscription_id - subscription was deleted")
                return {
                    "status": "subscription_ended",
                    "trial_expired": True,
                    "days_left": 0,
                    "should_cleanup": True,
                    "subscription_end": subscription_end
                }
        
        # Calculate trial end date with timezone consistency
        trial_start = user.trial_start or user.create_at
        # FIXED: Always calculate trial_end if missing, regardless of subscription_status
        # This prevents the contradiction where trial_end=None but user has "trial" status
        trial_end = user.trial_end
        if not trial_end and trial_start:
            # Auto-calculate trial_end if missing (7 days from trial_start)
            trial_end = trial_start + timedelta(days=self.trial_duration_days)

        # Ensure timezone consistency for comparisons
        if trial_start and trial_start.tzinfo is None:
            trial_start = trial_start.replace(tzinfo=timezone.utc)
        if trial_end and trial_end.tzinfo is None:
            trial_end = trial_end.replace(tzinfo=timezone.utc)

        # Check if trial has expired
        trial_expired = now > trial_end if trial_end else False
        # FIXED: Use total_seconds() for accurate days calculation
        if trial_end:
            remaining_seconds = (trial_end - now).total_seconds()
            days_left = max(0, int(remaining_seconds / 86400))  # 86400 seconds = 1 day
        else:
            days_left = 0

        # CRITICAL: Block access for ALL these cases:
        # 1. Trial expired AND no active subscription
        # 2. No subscription status (null/empty)
        # 3. Subscription status is anything other than "active", "trial", or "canceled" (with valid end date)
        # 4. Trial end date is missing (suspicious)
        # 5. Canceled subscription that has actually expired

        has_active_subscription = user.subscription_status == "active"
        has_valid_trial = trial_end and not trial_expired

        # Check if canceled subscription is still valid
        has_valid_canceled_subscription = False
        if user.subscription_status == "canceled" and user.subscription_end:
            subscription_end = user.subscription_end
            if subscription_end.tzinfo is None:
                subscription_end = subscription_end.replace(tzinfo=timezone.utc)
            has_valid_canceled_subscription = now < subscription_end

        # VALID SUBSCRIPTION STATUSES: Include "admin" for admin users
        valid_subscription_statuses = ["active", "trial", "canceled", "admin"]

        # Should cleanup (block access) if:
        should_cleanup = (
            # Trial expired and no active subscription and no valid canceled subscription
            (trial_expired and not has_active_subscription and not has_valid_canceled_subscription) or
            # No subscription status at all (null, empty, or invalid)
            (not user.subscription_status or user.subscription_status not in valid_subscription_statuses) or
            # Subscription status is not active/trial/admin and no valid trial and no valid canceled subscription
            (user.subscription_status not in ["active", "trial", "admin"] and not has_valid_trial and not has_valid_canceled_subscription) or
            # Missing trial end date for trial users (data integrity issue)
            (user.subscription_status == "trial" and not trial_end) or
            # Canceled subscription that has expired
            (user.subscription_status == "canceled" and user.subscription_end and now >= subscription_end)
        )

        # CRITICAL DEBUG: Log why access is being blocked
        if should_cleanup:
            logger.warning(f"🚫 BLOCKING ACCESS for user {user.username}: subscription_status={user.subscription_status}, subscription_id={user.subscription_id}, trial_expired={trial_expired}, has_active_subscription={has_active_subscription}, has_valid_trial={has_valid_trial}, has_valid_canceled_subscription={has_valid_canceled_subscription}")

        return {
            "status": "trial" if not trial_expired else "expired",
            "trial_expired": trial_expired,
            "days_left": days_left,
            "should_cleanup": should_cleanup,
            "trial_end": trial_end
        }
    
    async def get_expired_trial_users(self, session: AsyncSession) -> List[User]:
        """Get all users whose trials have expired and don't have active subscriptions."""
        now = datetime.now(timezone.utc)
        cutoff_date = now - timedelta(days=self.trial_duration_days)
        
        # Find users whose trial has expired
        stmt = select(User).where(
            User.create_at < cutoff_date,
            User.subscription_status != "active",
            User.is_superuser == False  # Don't cleanup superusers
        )
        
        result = await session.exec(stmt)
        expired_users = result.all()
        
        # Filter users whose trial has actually expired
        truly_expired = []
        for user in expired_users:
            trial_status = await self.check_trial_status(user)
            if trial_status["should_cleanup"]:
                truly_expired.append(user)
        
        return truly_expired
    
    async def cleanup_expired_user(self, user: User, session: AsyncSession) -> bool:
        """Cleanup an expired user account."""
        try:
            logger.info(f"Cleaning up expired user: {user.username} (ID: {user.id})")
            
            # Instead of deleting, we'll deactivate the user
            # This preserves data integrity while preventing access
            user.is_active = False
            user.subscription_status = "expired"
            
            await session.commit()
            logger.info(f"Successfully deactivated expired user: {user.username}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to cleanup user {user.username}: {e}")
            await session.rollback()
            return False
    
    async def cleanup_expired_trials(self) -> int:
        """Cleanup all expired trial users. Returns number of users cleaned up."""
        cleanup_count = 0
        
        try:
            db_service = get_db_service()
            async with db_service.with_session() as session:
                expired_users = await self.get_expired_trial_users(session)
                
                logger.info(f"Found {len(expired_users)} expired trial users to cleanup")
                
                for user in expired_users:
                    success = await self.cleanup_expired_user(user, session)
                    if success:
                        cleanup_count += 1
                
                logger.info(f"Successfully cleaned up {cleanup_count} expired trial users")
                
        except Exception as e:
            logger.error(f"Error during trial cleanup: {e}")
        
        return cleanup_count
    
    async def extend_trial(self, user_id: str, additional_days: int, session: AsyncSession) -> bool:
        """Extend a user's trial by additional days."""
        try:
            user = await get_user_by_id(session, user_id)
            if not user:
                return False
            
            # Calculate new trial end date with timezone consistency
            current_trial_end = user.trial_end or (user.trial_start + timedelta(days=self.trial_duration_days))

            # Ensure timezone consistency
            if current_trial_end and current_trial_end.tzinfo is None:
                current_trial_end = current_trial_end.replace(tzinfo=timezone.utc)

            new_trial_end = current_trial_end + timedelta(days=additional_days)
            
            user.trial_end = new_trial_end
            await session.commit()
            
            logger.info(f"Extended trial for user {user.username} by {additional_days} days")
            return True
            
        except Exception as e:
            logger.error(f"Failed to extend trial for user {user_id}: {e}")
            await session.rollback()
            return False
    
    async def reactivate_user(self, user_id: str, session: AsyncSession) -> bool:
        """Reactivate a user who was deactivated due to expired trial."""
        try:
            user = await get_user_by_id(session, user_id)
            if not user:
                return False
            
            user.is_active = True
            user.subscription_status = "trial"
            user.trial_start = datetime.now(timezone.utc)
            user.trial_end = None  # Will be calculated based on trial_start
            
            await session.commit()
            
            logger.info(f"Reactivated user {user.username}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to reactivate user {user_id}: {e}")
            await session.rollback()
            return False


# Global instance
trial_service = TrialService()


async def run_trial_cleanup_task():
    """Background task to cleanup expired trials."""
    while True:
        try:
            logger.info("Running trial cleanup task...")
            cleanup_count = await trial_service.cleanup_expired_trials()
            logger.info(f"Trial cleanup completed. Cleaned up {cleanup_count} users.")
            
            # Run cleanup every 24 hours
            await asyncio.sleep(24 * 60 * 60)
            
        except Exception as e:
            logger.error(f"Error in trial cleanup task: {e}")
            # Wait 1 hour before retrying on error
            await asyncio.sleep(60 * 60)
