"""
Email Verification Middleware
This middleware automatically handles verification issues and ensures
users are properly activated after email verification.
"""

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from axiestudio.logging import logger
from datetime import datetime, timezone


class EmailVerificationMiddleware(BaseHTTPMiddleware):
    """Middleware to automatically handle email verification issues."""

    def __init__(self, app):
        super().__init__(app)
        # Paths that trigger verification checks
        self.verification_paths = {
            "/api/v1/email/verify",
            "/api/v1/login",
        }

    async def dispatch(self, request: Request, call_next):
        """Check and fix verification issues on relevant endpoints."""
        
        # Only check on verification-related endpoints
        if not any(path in str(request.url.path) for path in self.verification_paths):
            return await call_next(request)

        # Process the request first
        response = await call_next(request)

        # If this was a verification endpoint, ensure user is properly activated
        if "/api/v1/email/verify" in str(request.url.path):
            await self._ensure_verification_completed(request)

        return response

    async def _ensure_verification_completed(self, request: Request):
        """Ensure email verification properly activates the user."""
        
        try:
            # Get the token from query params
            token = request.query_params.get("token")
            if not token:
                return

            from axiestudio.services.deps import get_db_service
            from axiestudio.services.database.models.user.model import User
            from sqlmodel import select

            db_service = get_db_service()
            
            async with db_service.with_session() as session:
                # Find user by token (even if token was cleared)
                stmt = select(User).where(User.email_verification_token == token)
                user = (await session.exec(stmt)).first()
                
                if not user:
                    # Token might have been cleared, try to find recently updated user
                    recent_time = datetime.now(timezone.utc).replace(second=0, microsecond=0)
                    stmt = select(User).where(
                        User.updated_at >= recent_time,
                        User.email_verified == True
                    )
                    user = (await session.exec(stmt)).first()

                if user:
                    # Ensure user is properly activated
                    needs_fix = False
                    
                    if not user.is_active and user.email_verified:
                        logger.warning(f"User {user.username} is verified but not active - fixing")
                        user.is_active = True
                        needs_fix = True
                    
                    if user.email_verification_token and user.email_verified:
                        logger.warning(f"User {user.username} is verified but still has token - clearing")
                        user.email_verification_token = None
                        user.email_verification_expires = None
                        needs_fix = True
                    
                    if needs_fix:
                        user.updated_at = datetime.now(timezone.utc)
                        await session.commit()
                        logger.info(f"Fixed verification state for user: {user.username}")

        except Exception as e:
            logger.error(f"Error in verification middleware: {e}")


# Add this to your main.py to enable the middleware
def add_verification_middleware(app):
    """Add the email verification middleware to the FastAPI app."""
    app.add_middleware(EmailVerificationMiddleware)
    logger.info("Email verification middleware enabled")
