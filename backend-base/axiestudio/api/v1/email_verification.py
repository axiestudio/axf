import secrets
import string
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Query, Depends, Request
from sqlmodel import select
from pydantic import BaseModel

from axiestudio.api.utils import DbSession
from axiestudio.services.database.models.user.model import User
from axiestudio.services.email.service import email_service
from axiestudio.services.auth.verification_code import validate_code, create_verification


# Import centralized timezone utility
from axiestudio.utils.timezone import ensure_timezone_aware

router = APIRouter(prefix="/email", tags=["Email Verification"])


class ResendEmailRequest(BaseModel):
    email: str


class ForgotPasswordRequest(BaseModel):
    email: str


class VerifyCodeRequest(BaseModel):
    """🎯 Request model for 6-digit code verification"""
    email: str
    code: str


class ResendCodeRequest(BaseModel):
    """🎯 Request model for resending 6-digit code"""
    email: str


@router.get("/verify")
async def verify_email(
    session: DbSession,
    token: str = Query(..., description="Email verification token"),
):
    """
    🎯 EMAIL VERIFICATION ENDPOINT
    This is called when user clicks "Confirm Email" button in their email.
    It MUST activate the user account automatically.
    """
    from axiestudio.logging import logger

    if not token:
        logger.warning("Email verification attempted without token")
        raise HTTPException(status_code=400, detail="Verification token is required")

    logger.info(f"🔍 Email verification attempt with token: {token[:8]}...")

    # Find user by verification token
    stmt = select(User).where(User.email_verification_token == token)
    user = (await session.exec(stmt)).first()

    if not user:
        logger.warning(f"❌ Invalid verification token: {token[:8]}...")
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired verification token. If you already verified your email, please try logging in directly."
        )

    logger.info(f"✅ Found user for verification: {user.username} (email: {user.email})")

    # Check if token has expired (with timezone-safe comparison)
    if user.email_verification_expires:
        user_expires = ensure_timezone_aware(user.email_verification_expires)
        if user_expires and user_expires < datetime.now(timezone.utc):
            logger.warning(f"⏰ Expired verification token for user: {user.username}")
            raise HTTPException(status_code=400, detail="Verification token has expired")

    # Log current state BEFORE verification
    logger.info(f"📊 BEFORE verification - User: {user.username}, is_active: {user.is_active}, email_verified: {user.email_verified}")

    try:
        # 🎯 CRITICAL: This is what happens when user clicks "Confirm Email"
        logger.info(f"🚀 ACTIVATING USER: {user.username}")

        # Step 1: Mark email as verified
        user.email_verified = True
        logger.info(f"✅ Set email_verified = True for {user.username}")

        # Step 2: ACTIVATE THE ACCOUNT - THIS IS THE KEY!
        user.is_active = True
        logger.info(f"🔓 Set is_active = True for {user.username}")

        # Step 3: Clear verification tokens
        user.email_verification_token = None
        user.email_verification_expires = None
        logger.info(f"🧹 Cleared verification tokens for {user.username}")

        # Step 4: Update timestamp
        user.updated_at = datetime.now(timezone.utc)

        # Step 5: Reset any failed login attempts
        if hasattr(user, 'failed_login_attempts'):
            user.failed_login_attempts = 0
        if hasattr(user, 'locked_until'):
            user.locked_until = None

        # Step 6: COMMIT TO DATABASE - CRITICAL!
        logger.info(f"💾 COMMITTING changes to database for {user.username}")
        await session.commit()
        await session.refresh(user)

        # Log final state AFTER verification
        logger.info(f"🎉 AFTER verification - User: {user.username}, is_active: {user.is_active}, email_verified: {user.email_verified}")
        logger.info(f"✅ USER {user.username} SUCCESSFULLY VERIFIED AND ACTIVATED!")

    except Exception as e:
        logger.error(f"❌ FAILED to verify user {user.username}: {e}")
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"Database error during verification: {str(e)}")

    # Generate access token for automatic login
    try:
        from axiestudio.services.auth.utils import create_user_tokens
        tokens = await create_user_tokens(user.id, session, update_last_login=True)
        logger.info(f"🔑 Generated access tokens for {user.username}")

        return {
            "message": "🎉 Email verified successfully! Your account is now active and you are logged in.",
            "verified": True,
            "activated": True,
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "token_type": "bearer",
            "user_id": str(user.id),
            "username": user.username,
            "email": user.email,
            "auto_login": True,
            "can_login": True
        }

    except Exception as e:
        logger.error(f"❌ Failed to generate tokens for {user.username}: {e}")
        # Don't fail verification if token generation fails
        return {
            "message": "Email verified successfully! Your account is active. Please log in manually.",
            "verified": True,
            "activated": True,
            "auto_login": False,
            "username": user.username,
            "email": user.email,
            "can_login": True
        }


@router.post("/resend-verification")
async def resend_verification_email(
    request: ResendEmailRequest,
    session: DbSession,
):
    """Resend verification email."""
    # Find user by email
    stmt = select(User).where(User.email == request.email)
    user = (await session.exec(stmt)).first()
    
    if not user:
        # 🔐 ENTERPRISE SECURITY: Prevent email enumeration
        # Always return success to prevent revealing if email exists
        logger.warning(f"❌ Forgot password attempted for non-existent email: {request.email}")
        return {
            "message": "If this email exists in our system, you will receive a password reset link.",
            "success": True
        }
    
    if user.email_verified:
        raise HTTPException(status_code=400, detail="Email is already verified")
    
    # Generate new verification token
    token = email_service.generate_verification_token()
    expiry = email_service.get_verification_expiry()
    
    # Update user with new token
    user.email_verification_token = token
    user.email_verification_expires = expiry
    user.updated_at = datetime.now(timezone.utc)
    
    await session.commit()
    
    # Send verification email
    email_sent = await email_service.send_verification_email(user.email, user.username, token)
    
    if not email_sent:
        raise HTTPException(status_code=500, detail="Failed to send verification email")
    
    return {
        "message": "Verification email sent successfully",
        "email": user.email
    }


@router.post("/forgot-password")
async def forgot_password(
    request: ForgotPasswordRequest,
    session: DbSession,
    http_request: Request,
):
    """Send login credentials email with enterprise security features."""
    from axiestudio.logging import logger

    # Get client IP for security logging
    client_ip = http_request.client.host if http_request.client else "unknown"

    # Find user by email
    stmt = select(User).where(User.email == request.email)
    user = (await session.exec(stmt)).first()

    # Always return success to prevent email enumeration attacks
    success_response = {
        "message": "If you own that email, you will receive the login credentials.",
        "email": request.email,
        "professional_notice": "For security reasons, we don't confirm whether this email exists in our system."
    }

    if not user:
        # Log suspicious activity for security monitoring
        logger.warning(f"Password reset attempted for non-existent email: {request.email} from IP: {client_ip}")
        return success_response

    if not user.is_active:
        # Log inactive user reset attempts
        logger.info(f"Password reset attempted for inactive user: {user.username} from IP: {client_ip}")
        return success_response

    # Check if user email is verified
    if not user.email_verified:
        # Log security event but still return success
        logger.warning(f"Login credentials requested for unverified email: {user.email}")
        return success_response

    # Rate limiting check (prevent abuse)
    from axiestudio.api.v1.subscriptions import check_rate_limit
    if not check_rate_limit(f"forgot_password_{client_ip}", "forgot_password"):
        logger.warning(f"Rate limit exceeded for login credentials request from IP: {client_ip}")
        return success_response

    # Generate a simple temporary password
    temp_password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(8))

    # Hash the temporary password and update user
    from axiestudio.services.auth.utils import get_password_hash
    user.password = get_password_hash(temp_password)
    user.updated_at = datetime.now(timezone.utc)

    # Set temporary password expiration (24 hours from now)
    temp_password_expires = datetime.now(timezone.utc) + timedelta(hours=24)
    user.email_verification_expires = temp_password_expires  # Reuse existing field for temp password expiry

    # Mark that user needs to change password on next login
    user.password_changed_at = None  # This will force password change

    await session.commit()

    # Log successful password reset for security audit
    logger.info(f"Temporary password generated for user: {user.username} from IP: {client_ip}")

    # Send temporary password email
    email_sent = await email_service.send_temporary_password_email(
        user.email,
        user.username,
        temp_password,
        client_ip=client_ip  # Pass IP for security notice in email
    )

    if not email_sent:
        # Log error but still return success to prevent enumeration
        logger.error(f"Failed to send temporary password email to {user.email} from IP: {client_ip}")

    return success_response


@router.get("/reset-password")
async def reset_password(
    session: DbSession,
    token: str = Query(..., description="Password reset token"),
):
    """Handle password reset token and log user in automatically."""
    if not token:
        raise HTTPException(status_code=400, detail="Reset token is required")

    # Find user by reset token (stored in email_verification_token field)
    stmt = select(User).where(User.email_verification_token == token)
    user = (await session.exec(stmt)).first()

    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    # Check if token has expired (with timezone-safe comparison)
    if user.email_verification_expires:
        user_expires = ensure_timezone_aware(user.email_verification_expires)
        if user_expires and user_expires < datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="Reset token has expired")

    # Activate the user if they're not active (password reset also serves as email verification)
    if not user.is_active:
        user.is_active = True
        user.email_verified = True  # Mark email as verified since they accessed the reset link

    # Clear the reset token
    user.email_verification_token = None
    user.email_verification_expires = None
    user.updated_at = datetime.now(timezone.utc)

    await session.commit()
    await session.refresh(user)

    # Generate access token for automatic login
    from axiestudio.services.auth.utils import create_user_tokens
    tokens = await create_user_tokens(user.id, session, update_last_login=True)

    return {
        "message": "Password reset successful! You are now logged in. Please set a new password.",
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "token_type": "bearer",
        "user_id": str(user.id),
        "username": user.username,
        "redirect_to_change_password": True,  # 🔐 ENTERPRISE: Redirect to change password page
        "redirect_url": "/change-password?from_reset=true"
    }


@router.get("/check-user/{username}")
async def check_user_status(
    username: str,
    session: DbSession,
):
    """
    🔍 Check user verification status for debugging.
    Use this to verify that email verification is working properly.
    """
    from axiestudio.logging import logger

    stmt = select(User).where(User.username == username)
    user = (await session.exec(stmt)).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    logger.info(f"📊 User status check for: {username}")

    return {
        "username": user.username,
        "email": user.email,
        "is_active": user.is_active,
        "email_verified": user.email_verified,
        "has_verification_token": user.email_verification_token is not None,
        "verification_expires": user.email_verification_expires,
        "created_at": user.create_at,
        "updated_at": user.updated_at,
        "last_login_at": user.last_login_at,
        "can_login": user.is_active and user.email_verified,
        "status": "✅ READY TO LOGIN" if (user.is_active and user.email_verified) else "❌ NEEDS VERIFICATION",
        "next_action": "User can login now" if (user.is_active and user.email_verified) else "User must click email verification link"
    }


@router.post("/verify-code")
async def verify_code(
    request: VerifyCodeRequest,
    session: DbSession,
):
    """
    🎯 ENTERPRISE 6-DIGIT CODE VERIFICATION ENDPOINT

    This is the NEW way users verify their email - by entering a 6-digit code
    instead of clicking a link. This is how Google, Microsoft, AWS, etc. do it.

    When user enters the 6-digit code:
    1. Validates the code format and expiry
    2. Checks rate limiting (max 5 attempts)
    3. Activates the user account (is_active = True)
    4. Marks email as verified (email_verified = True)
    5. Auto-logs the user in
    """
    from axiestudio.logging import logger

    logger.info(f"🔍 6-digit code verification attempt for email: {request.email}")

    # Find user by email
    stmt = select(User).where(User.email == request.email)
    user = (await session.exec(stmt)).first()

    if not user:
        # 🔐 ENTERPRISE SECURITY: Prevent email enumeration
        # Return generic error without revealing email existence
        logger.warning(f"❌ Code verification attempted for non-existent email: {request.email}")
        raise HTTPException(
            status_code=400,
            detail="Invalid verification code or email address"
        )

    logger.info(f"✅ Found user for code verification: {user.username}")

    # Check if user is already verified
    if user.email_verified and user.is_active:
        logger.info(f"🔄 User {user.username} already verified and active")
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Email already verified. You can login now.",
                "verified": True,
                "can_login": True,
                "action": "login_now"
            }
        )

    # Validate the 6-digit code using our enterprise service
    validation_result = validate_code(
        code=request.code,
        stored_code=user.verification_code,
        expiry=user.verification_code_expires,
        attempts=user.verification_attempts
    )

    # Handle validation failure
    if not validation_result["valid"]:
        # Increment failed attempts
        user.verification_attempts += 1
        await session.commit()

        logger.warning(f"❌ Invalid code for {user.username}: {validation_result['error']}")

        raise HTTPException(
            status_code=400,
            detail={
                "message": validation_result["error"],
                "remaining_attempts": validation_result["remaining_attempts"],
                "rate_limited": validation_result["rate_limited"],
                "expired": validation_result["expired"]
            }
        )

    # 🎉 SUCCESS - Activate the user account!
    try:
        logger.info(f"🚀 ACTIVATING USER ACCOUNT: {user.username}")

        # Step 1: Mark email as verified
        user.email_verified = True
        logger.info(f"✅ Set email_verified = True for {user.username}")

        # Step 2: ACTIVATE THE ACCOUNT - THIS IS THE KEY!
        user.is_active = True
        logger.info(f"🔓 Set is_active = True for {user.username}")

        # Step 3: Clear verification codes and reset attempts
        user.verification_code = None
        user.verification_code_expires = None
        user.verification_attempts = 0
        logger.info(f"🧹 Cleared verification codes for {user.username}")

        # Step 4: Clear legacy token fields too
        user.email_verification_token = None
        user.email_verification_expires = None

        # Step 5: Update timestamp
        user.updated_at = datetime.now(timezone.utc)

        # Step 6: Reset any failed login attempts
        if hasattr(user, 'failed_login_attempts'):
            user.failed_login_attempts = 0
        if hasattr(user, 'locked_until'):
            user.locked_until = None

        # Step 7: COMMIT TO DATABASE - CRITICAL!
        logger.info(f"💾 COMMITTING account activation to database for {user.username}")
        await session.commit()
        await session.refresh(user)

        logger.info(f"🎉 USER {user.username} SUCCESSFULLY VERIFIED AND ACTIVATED!")

    except Exception as e:
        logger.error(f"❌ FAILED to activate user {user.username}: {e}")
        await session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Database error during account activation: {str(e)}"
        )

    # Generate access tokens for automatic login
    try:
        from axiestudio.services.auth.utils import create_user_tokens
        tokens = await create_user_tokens(user.id, session, update_last_login=True)
        logger.info(f"🔑 Generated access tokens for {user.username}")

        return {
            "message": "🎉 Email verified successfully! Your account is now active and you are logged in.",
            "verified": True,
            "activated": True,
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "token_type": "bearer",
            "user_id": str(user.id),
            "username": user.username,
            "email": user.email,
            "auto_login": True,
            "can_login": True,
            "redirect_to": "/dashboard"
        }

    except Exception as e:
        logger.error(f"❌ Failed to generate tokens for {user.username}: {e}")
        # Don't fail verification if token generation fails
        return {
            "message": "✅ Email verified successfully! Your account is active. Please log in manually.",
            "verified": True,
            "activated": True,
            "auto_login": False,
            "username": user.username,
            "email": user.email,
            "can_login": True,
            "redirect_to": "/login"
        }


@router.post("/resend-code")
async def resend_verification_code(
    request: ResendCodeRequest,
    session: DbSession,
    http_request: Request,
):
    """
    🔄 Resend 6-digit verification code

    Generates a new 6-digit code and sends it via email.
    Resets the attempt counter for security.
    """
    from axiestudio.logging import logger

    logger.info(f"🔄 Resend code request for email: {request.email}")

    # 🛡️ ENTERPRISE SECURITY: Rate limiting for resend endpoint
    client_ip = http_request.client.host if http_request.client else "unknown"

    # Basic rate limiting for resend endpoint (prevent spam)
    from axiestudio.api.v1.subscriptions import check_rate_limit
    if not check_rate_limit(f"resend_{client_ip}", "resend"):
        raise HTTPException(
            status_code=429,
            detail="Too many resend attempts from this location. Please wait before trying again."
        )

    # Find user by email
    stmt = select(User).where(User.email == request.email)
    user = (await session.exec(stmt)).first()

    if not user:
        # 🔐 ENTERPRISE SECURITY: Prevent email enumeration
        # Always return success to prevent revealing if email exists
        logger.warning(f"❌ Resend code requested for non-existent email: {request.email}")
        return {
            "message": "If this email exists in our system, a new verification code has been sent.",
            "success": True
        }

    # Check if user is already verified
    if user.email_verified and user.is_active:
        logger.info(f"🔄 Resend code requested for already verified user: {user.username}")
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Email already verified. You can login now.",
                "verified": True,
                "can_login": True,
                "action": "login_now"
            }
        )

    try:
        # Generate new 6-digit code
        new_code, code_expiry = create_verification()

        # Update user with new code
        user.verification_code = new_code
        user.verification_code_expires = code_expiry
        user.verification_attempts = 0  # Reset attempts
        user.updated_at = datetime.now(timezone.utc)

        await session.commit()

        # Send new verification code email
        email_sent = await email_service.send_verification_code_email(
            user.email, user.username, new_code
        )

        if not email_sent:
            logger.error(f"❌ Failed to send verification code to {user.email}")
            raise HTTPException(
                status_code=500,
                detail={
                    "message": "Failed to send verification code",
                    "action": "try_again_later"
                }
            )

        logger.info(f"✅ New verification code sent to {user.email}")

        return {
            "message": "New verification code sent successfully!",
            "email": user.email,
            "expires_in": "10 minutes",
            "max_attempts": 5,
            "check_spam": True
        }

    except Exception as e:
        logger.error(f"❌ Error resending verification code to {user.email}: {e}")
        await session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to resend verification code: {str(e)}"
        )
