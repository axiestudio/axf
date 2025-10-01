"""
Trial Ending Notification Service
Sends automated emails to users when their trial is ending
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from sqlmodel import Session, select
from axiestudio.logging import logger

from axiestudio.services.database.models.user.model import User
from axiestudio.services.email.service import EmailService
from axiestudio.services.trial.service import trial_service


class TrialNotificationService:
    """
    Service for sending trial ending notifications.
    
    Features:
    - Send notifications at 3 days, 1 day, and day of expiry
    - Track which notifications have been sent to avoid spam
    - Batch processing for efficiency
    """
    
    def __init__(self):
        self.email_service = EmailService()
        self.trial_service = trial_service
        self._sent_notifications = set()  # Simple in-memory cache
    
    async def check_and_send_trial_notifications(self, session: Session) -> int:
        """
        Check all users and send trial ending notifications as needed.
        
        Returns:
            int: Number of notifications sent
        """
        try:
            notifications_sent = 0
            
            # Get all users with active trials
            stmt = select(User).where(
                User.subscription_status == "trial",
                User.is_active == True,
                User.email.isnot(None)
            )
            users = (await session.exec(stmt)).all()
            
            logger.info(f"🔍 Checking {len(users)} trial users for notifications")
            
            for user in users:
                try:
                    # Get trial status for this user
                    trial_status = await self.trial_service.get_trial_status(session, user.id)
                    
                    if trial_status.get("trial_expired", False):
                        continue  # Skip expired trials
                    
                    days_left = trial_status.get("days_left", 0)
                    
                    # Check if we should send a notification
                    if await self._should_send_notification(user, days_left):
                        success = await self.email_service.send_trial_ending_email(
                            email=user.email,
                            username=user.username,
                            days_left=days_left
                        )
                        
                        if success:
                            self._mark_notification_sent(user.id, days_left)
                            notifications_sent += 1
                            logger.info(f"📧 Sent trial ending notification to {user.username} ({days_left} days left)")
                        else:
                            logger.error(f"❌ Failed to send trial notification to {user.username}")
                
                except Exception as e:
                    logger.error(f"Error processing trial notification for user {user.id}: {e}")
                    continue
            
            logger.info(f"✅ Sent {notifications_sent} trial ending notifications")
            return notifications_sent
            
        except Exception as e:
            logger.error(f"Error in trial notification check: {e}")
            return 0
    
    async def _should_send_notification(self, user: User, days_left: int) -> bool:
        """Check if we should send a notification for this user and days left."""
        try:
            # Send notifications at specific intervals
            notification_days = [3, 1, 0]  # 3 days, 1 day, day of expiry
            
            if days_left not in notification_days:
                return False
            
            # Check if we've already sent this notification
            notification_key = f"{user.id}:{days_left}"
            if notification_key in self._sent_notifications:
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking notification eligibility: {e}")
            return False
    
    def _mark_notification_sent(self, user_id: int, days_left: int) -> None:
        """Mark that we've sent a notification to prevent duplicates."""
        try:
            notification_key = f"{user_id}:{days_left}"
            self._sent_notifications.add(notification_key)
            
            # Clean up old notifications (keep only last 1000)
            if len(self._sent_notifications) > 1000:
                # Convert to list, sort, and keep only newest 500
                notifications_list = list(self._sent_notifications)
                self._sent_notifications = set(notifications_list[-500:])
                
        except Exception as e:
            logger.error(f"Error marking notification as sent: {e}")
    
    async def send_immediate_trial_notification(
        self, 
        session: Session, 
        user_id: int
    ) -> bool:
        """
        Send an immediate trial notification for a specific user.
        Useful for testing or manual triggers.
        """
        try:
            # Get user
            stmt = select(User).where(User.id == user_id)
            user = (await session.exec(stmt)).first()
            
            if not user or not user.email:
                logger.warning(f"Cannot send trial notification: user {user_id} not found or no email")
                return False
            
            # Get trial status
            trial_status = await self.trial_service.get_trial_status(session, user_id)
            days_left = trial_status.get("days_left", 0)
            
            if trial_status.get("trial_expired", False):
                logger.warning(f"Cannot send trial notification: user {user_id} trial already expired")
                return False
            
            # Send notification
            success = await self.email_service.send_trial_ending_email(
                email=user.email,
                username=user.username,
                days_left=days_left
            )
            
            if success:
                logger.info(f"📧 Sent immediate trial notification to {user.username}")
                return True
            else:
                logger.error(f"❌ Failed to send immediate trial notification to {user.username}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending immediate trial notification: {e}")
            return False
    
    async def get_notification_stats(self, session: Session) -> dict:
        """Get statistics about trial notifications."""
        try:
            # Count users by trial status
            stmt = select(User).where(
                User.subscription_status == "trial",
                User.is_active == True
            )
            trial_users = (await session.exec(stmt)).all()
            
            stats = {
                "total_trial_users": len(trial_users),
                "users_with_email": len([u for u in trial_users if u.email]),
                "notifications_sent_today": len(self._sent_notifications),
                "notification_breakdown": {}
            }
            
            # Breakdown by days left
            for user in trial_users:
                if not user.email:
                    continue
                    
                try:
                    trial_status = await self.trial_service.get_trial_status(session, user.id)
                    days_left = trial_status.get("days_left", 0)
                    
                    if days_left not in stats["notification_breakdown"]:
                        stats["notification_breakdown"][days_left] = 0
                    stats["notification_breakdown"][days_left] += 1
                    
                except Exception:
                    continue
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting notification stats: {e}")
            return {"error": str(e)}


# Global instance
trial_notification_service = TrialNotificationService()


def get_trial_notification_service() -> TrialNotificationService:
    """Get the global trial notification service instance."""
    return trial_notification_service


async def run_trial_notification_check():
    """
    Standalone function to run trial notification check.
    Can be called from a cron job or scheduled task.
    """
    try:
        from axiestudio.services.database.service import get_db_service
        
        async with get_db_service().with_session() as session:
            service = get_trial_notification_service()
            notifications_sent = await service.check_and_send_trial_notifications(session)
            logger.info(f"🎯 Trial notification check complete: {notifications_sent} notifications sent")
            return notifications_sent
            
    except Exception as e:
        logger.error(f"Error in trial notification check: {e}")
        return 0


if __name__ == "__main__":
    # Allow running this script directly for testing
    import asyncio
    asyncio.run(run_trial_notification_check())
