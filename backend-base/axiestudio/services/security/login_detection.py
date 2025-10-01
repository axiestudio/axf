"""
Login Detection and Security Notification Service
Tracks user logins and sends security notifications for new devices/locations
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from sqlmodel import Session, select
from axiestudio.logging import logger

from axiestudio.services.database.models.user.model import User
from axiestudio.services.email.service import EmailService


class LoginDetectionService:
    """
    Service for detecting new logins and sending security notifications.
    
    Features:
    - Track login patterns by IP, location, device
    - Detect suspicious login attempts
    - Send security notification emails
    - Rate limiting for notifications
    """
    
    def __init__(self):
        self.email_service = EmailService()
        self._notification_cache = {}  # Simple in-memory cache for rate limiting
    
    async def track_login(
        self, 
        session: Session, 
        user: User, 
        client_ip: str, 
        user_agent: str = "unknown"
    ) -> bool:
        """
        Track a user login and send notification if it's from a new device/location.
        
        Args:
            session: Database session
            user: User object
            client_ip: Client IP address
            user_agent: User agent string
            
        Returns:
            bool: True if notification was sent, False otherwise
        """
        try:
            # Parse device info from user agent
            device_info = self._parse_user_agent(user_agent)
            
            # Get location info from IP (simplified - in production use a geolocation service)
            location_info = await self._get_location_from_ip(client_ip)
            
            # Check if this is a new login pattern
            is_new_login = await self._is_new_login_pattern(
                session, user, client_ip, device_info
            )
            
            # Update user's last login info
            await self._update_last_login(session, user, client_ip, user_agent)
            
            # Send notification if it's a new login and we haven't sent one recently
            if is_new_login and await self._should_send_notification(user.id, client_ip):
                await self._send_login_notification(
                    user, client_ip, location_info, device_info
                )
                
                # Cache this notification to prevent spam
                self._cache_notification(user.id, client_ip)
                
                logger.info(f"🔔 Sent new login notification to {user.username} from {client_ip}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error tracking login for user {user.username}: {e}")
            return False
    
    def _parse_user_agent(self, user_agent: str) -> Dict[str, str]:
        """Parse user agent string to extract device/browser info."""
        try:
            # Simplified user agent parsing
            device_info = {
                "browser": "Unknown",
                "os": "Unknown",
                "device": "Unknown"
            }
            
            user_agent_lower = user_agent.lower()
            
            # Detect browser
            if "chrome" in user_agent_lower:
                device_info["browser"] = "Chrome"
            elif "firefox" in user_agent_lower:
                device_info["browser"] = "Firefox"
            elif "safari" in user_agent_lower:
                device_info["browser"] = "Safari"
            elif "edge" in user_agent_lower:
                device_info["browser"] = "Edge"
            
            # Detect OS
            if "windows" in user_agent_lower:
                device_info["os"] = "Windows"
            elif "mac" in user_agent_lower:
                device_info["os"] = "macOS"
            elif "linux" in user_agent_lower:
                device_info["os"] = "Linux"
            elif "android" in user_agent_lower:
                device_info["os"] = "Android"
            elif "ios" in user_agent_lower:
                device_info["os"] = "iOS"
            
            # Detect device type
            if "mobile" in user_agent_lower:
                device_info["device"] = "Mobile"
            elif "tablet" in user_agent_lower:
                device_info["device"] = "Tablet"
            else:
                device_info["device"] = "Desktop"
            
            return device_info
            
        except Exception as e:
            logger.error(f"Error parsing user agent: {e}")
            return {"browser": "Unknown", "os": "Unknown", "device": "Unknown"}
    
    async def _get_location_from_ip(self, client_ip: str) -> Dict[str, str]:
        """Get location information from IP address."""
        try:
            # In production, use a real geolocation service like:
            # - MaxMind GeoIP2
            # - ipapi.co
            # - ipgeolocation.io
            
            # For now, return simplified location info
            if client_ip.startswith("192.168.") or client_ip.startswith("10.") or client_ip.startswith("127."):
                return {
                    "country": "Local Network",
                    "city": "Private IP",
                    "region": "LAN"
                }
            
            # Simplified location detection based on IP ranges
            # This is just for demo - use a real service in production
            return {
                "country": "Unknown",
                "city": "Unknown", 
                "region": "Unknown"
            }
            
        except Exception as e:
            logger.error(f"Error getting location for IP {client_ip}: {e}")
            return {"country": "Unknown", "city": "Unknown", "region": "Unknown"}
    
    async def _is_new_login_pattern(
        self, 
        session: Session, 
        user: User, 
        client_ip: str, 
        device_info: Dict[str, str]
    ) -> bool:
        """Check if this login represents a new pattern for the user."""
        try:
            # Check if user has logged in from this IP in the last 30 days
            # In a real implementation, you'd store login history in the database
            
            # For now, consider it "new" if:
            # 1. User's last_login_ip is different
            # 2. Or if it's been more than 7 days since last login
            
            if not hasattr(user, 'last_login_ip') or not user.last_login_ip:
                return True  # First login or no IP recorded
            
            if user.last_login_ip != client_ip:
                return True  # Different IP
            
            # Check if it's been a while since last login
            if hasattr(user, 'last_login_at') and user.last_login_at:
                # Ensure timezone-aware comparison to prevent offset-naive vs offset-aware errors
                from axiestudio.utils.timezone import ensure_timezone_aware
                last_login_aware = ensure_timezone_aware(user.last_login_at)
                now = datetime.now(timezone.utc)

                if last_login_aware:
                    time_since_last = now - last_login_aware
                    if time_since_last > timedelta(days=7):
                        return True  # Been a while
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking login pattern: {e}")
            return False
    
    async def _update_last_login(
        self, 
        session: Session, 
        user: User, 
        client_ip: str, 
        user_agent: str
    ) -> None:
        """Update user's last login information."""
        try:
            # Update user's login tracking fields
            user.last_login_at = datetime.now(timezone.utc)
            user.last_login_ip = client_ip
            
            # In a real implementation, you might want to store this in a separate table
            # to maintain a full login history
            
            await session.commit()
            
        except Exception as e:
            logger.error(f"Error updating last login for user {user.username}: {e}")
    
    async def _should_send_notification(self, user_id: int, client_ip: str) -> bool:
        """Check if we should send a notification (rate limiting)."""
        try:
            cache_key = f"{user_id}:{client_ip}"
            
            # Check if we've sent a notification for this user/IP in the last 24 hours
            if cache_key in self._notification_cache:
                last_notification = self._notification_cache[cache_key]
                time_since = datetime.now(timezone.utc) - last_notification
                
                if time_since < timedelta(hours=24):
                    return False  # Don't spam notifications
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking notification rate limit: {e}")
            return False
    
    def _cache_notification(self, user_id: int, client_ip: str) -> None:
        """Cache that we sent a notification to prevent spam."""
        try:
            cache_key = f"{user_id}:{client_ip}"
            self._notification_cache[cache_key] = datetime.now(timezone.utc)
            
            # Clean up old cache entries (keep only last 1000 entries)
            if len(self._notification_cache) > 1000:
                # Remove oldest entries
                sorted_items = sorted(
                    self._notification_cache.items(), 
                    key=lambda x: x[1]
                )
                # Keep only the newest 500 entries
                self._notification_cache = dict(sorted_items[-500:])
                
        except Exception as e:
            logger.error(f"Error caching notification: {e}")
    
    async def _send_login_notification(
        self, 
        user: User, 
        client_ip: str, 
        location_info: Dict[str, str], 
        device_info: Dict[str, str]
    ) -> None:
        """Send login notification email to user."""
        try:
            if not user.email:
                logger.warning(f"Cannot send login notification to {user.username}: no email")
                return
            
            # Format location and device strings
            location = f"{location_info['city']}, {location_info['country']}"
            if location_info['city'] == "Unknown":
                location = location_info['country']
            
            device = f"{device_info['browser']} on {device_info['os']} ({device_info['device']})"
            
            # Send the notification email
            success = await self.email_service.send_new_login_detected_email(
                email=user.email,
                username=user.username,
                client_ip=client_ip,
                location=location,
                device=device
            )
            
            if success:
                logger.info(f"✅ Login notification sent to {user.username}")
            else:
                logger.error(f"❌ Failed to send login notification to {user.username}")
                
        except Exception as e:
            logger.error(f"Error sending login notification: {e}")


# Global instance
login_detection_service = LoginDetectionService()


def get_login_detection_service() -> LoginDetectionService:
    """Get the global login detection service instance."""
    return login_detection_service
