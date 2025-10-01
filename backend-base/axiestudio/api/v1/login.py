from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from axiestudio.api.utils import DbSession
from axiestudio.api.v1.schemas import Token
from axiestudio.initial_setup.setup import get_or_create_default_folder
from axiestudio.services.auth.utils import (
    authenticate_user,
    create_refresh_token,
    create_user_longterm_token,
    create_user_tokens,
    get_current_active_user,
    verify_password,
    get_password_hash,
)
from axiestudio.services.database.models.user.crud import get_user_by_id
from axiestudio.services.database.models.user.model import User
from axiestudio.services.deps import get_settings_service, get_variable_service

router = APIRouter(tags=["Login"])


class ChangePasswordRequest(BaseModel):
    """Request model for changing password."""
    current_password: str | None = None  # Optional for password reset flow
    new_password: str


class ChangePasswordResponse(BaseModel):
    """Response model for password change."""
    success: bool
    message: str


@router.post("/login", response_model=Token)
async def login_to_get_access_token(
    response: Response,
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: DbSession,
):
    auth_settings = get_settings_service().auth_settings

    # Get client IP and user agent for security logging
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("User-Agent", "unknown")

    try:
        user = await authenticate_user(form_data.username, form_data.password, db, client_ip, user_agent)
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    if user:
        # Check if user needs to change password (temporary password scenario)
        password_change_required = user.password_changed_at is None

        # 🔐 ENTERPRISE: Update login tracking with IP and timestamp
        client_ip = request.client.host if request.client else "unknown"
        user.last_login_at = datetime.now(timezone.utc)
        user.last_login_ip = client_ip
        user.failed_login_attempts = 0  # Reset failed attempts on successful login
        user.locked_until = None  # Clear any account locks

        # Commit login tracking updates
        db.add(user)
        await db.commit()
        await db.refresh(user)

        tokens = await create_user_tokens(user_id=user.id, db=db, update_last_login=True)

        # Add password change requirement to response
        if password_change_required:
            tokens["password_change_required"] = True
            tokens["message"] = "Password change required. Please update your password."
        response.set_cookie(
            "refresh_token_as",
            tokens["refresh_token"],
            httponly=auth_settings.REFRESH_HTTPONLY,
            samesite=auth_settings.REFRESH_SAME_SITE,
            secure=auth_settings.REFRESH_SECURE,
            expires=auth_settings.REFRESH_TOKEN_EXPIRE_SECONDS,
            domain=auth_settings.COOKIE_DOMAIN,
        )
        response.set_cookie(
            "access_token_as",
            tokens["access_token"],
            httponly=auth_settings.ACCESS_HTTPONLY,
            samesite=auth_settings.ACCESS_SAME_SITE,
            secure=auth_settings.ACCESS_SECURE,
            expires=auth_settings.ACCESS_TOKEN_EXPIRE_SECONDS,
            domain=auth_settings.COOKIE_DOMAIN,
        )
        response.set_cookie(
            "apikey_tkn_axie",
            str(user.store_api_key),
            httponly=auth_settings.ACCESS_HTTPONLY,
            samesite=auth_settings.ACCESS_SAME_SITE,
            secure=auth_settings.ACCESS_SECURE,
            expires=None,  # Set to None to make it a session cookie
            domain=auth_settings.COOKIE_DOMAIN,
        )
        await get_variable_service().initialize_user_variables(user.id, db)
        # Create default project for user if it doesn't exist
        _ = await get_or_create_default_folder(db, user.id)
        return tokens
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect username or password",
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.get("/auto_login")
async def auto_login(response: Response, db: DbSession):
    auth_settings = get_settings_service().auth_settings

    if auth_settings.AUTO_LOGIN:
        user_id, tokens = await create_user_longterm_token(db)
        response.set_cookie(
            "access_token_as",
            tokens["access_token"],
            httponly=auth_settings.ACCESS_HTTPONLY,
            samesite=auth_settings.ACCESS_SAME_SITE,
            secure=auth_settings.ACCESS_SECURE,
            expires=None,  # Set to None to make it a session cookie
            domain=auth_settings.COOKIE_DOMAIN,
        )

        user = await get_user_by_id(db, user_id)

        if user:
            if user.store_api_key is None:
                user.store_api_key = ""

            response.set_cookie(
                "apikey_tkn_axie",
                str(user.store_api_key),  # Ensure it's a string
                httponly=auth_settings.ACCESS_HTTPONLY,
                samesite=auth_settings.ACCESS_SAME_SITE,
                secure=auth_settings.ACCESS_SECURE,
                expires=None,  # Set to None to make it a session cookie
                domain=auth_settings.COOKIE_DOMAIN,
            )

        return tokens

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "message": "Auto login is disabled. Please enable it in the settings",
            "auto_login": False,
        },
    )


@router.post("/refresh")
async def refresh_token(
    request: Request,
    response: Response,
    db: DbSession,
):
    auth_settings = get_settings_service().auth_settings

    token = request.cookies.get("refresh_token_as")

    if token:
        tokens = await create_refresh_token(token, db)
        response.set_cookie(
            "refresh_token_as",
            tokens["refresh_token"],
            httponly=auth_settings.REFRESH_HTTPONLY,
            samesite=auth_settings.REFRESH_SAME_SITE,
            secure=auth_settings.REFRESH_SECURE,
            expires=auth_settings.REFRESH_TOKEN_EXPIRE_SECONDS,
            domain=auth_settings.COOKIE_DOMAIN,
        )
        response.set_cookie(
            "access_token_as",
            tokens["access_token"],
            httponly=auth_settings.ACCESS_HTTPONLY,
            samesite=auth_settings.ACCESS_SAME_SITE,
            secure=auth_settings.ACCESS_SECURE,
            expires=auth_settings.ACCESS_TOKEN_EXPIRE_SECONDS,
            domain=auth_settings.COOKIE_DOMAIN,
        )
        return tokens
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("refresh_token_as")
    response.delete_cookie("access_token_as")
    response.delete_cookie("apikey_tkn_axie")
    return {"message": "Logout successful"}


@router.post("/change-password", response_model=ChangePasswordResponse)
async def change_password(
    request: ChangePasswordRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: DbSession,
):
    """
    Change user password.

    For normal password change: requires current_password
    For password reset flow: current_password is optional (user already authenticated via reset token)
    """
    try:
        # Validate new password strength
        if len(request.new_password) < 8:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password must be at least 8 characters long"
            )

        # Check for password complexity
        import re
        if not re.search(r'[A-Z]', request.new_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password must contain at least one uppercase letter"
            )

        if not re.search(r'[a-z]', request.new_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password must contain at least one lowercase letter"
            )

        if not re.search(r'\d', request.new_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password must contain at least one number"
            )

        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', request.new_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password must contain at least one special character"
            )

        # If current_password is provided, verify it
        if request.current_password:
            if not verify_password(request.current_password, current_user.password):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Current password is incorrect"
                )

        # Hash new password
        new_password_hash = get_password_hash(request.new_password)

        # 🔐 ENTERPRISE: Update user password in database with timestamp tracking
        current_user.password = new_password_hash
        current_user.password_changed_at = datetime.now(timezone.utc)  # CRITICAL: Track password change
        current_user.updated_at = datetime.now(timezone.utc)  # Update general timestamp

        # Clear temporary password expiration (if this was a temp password change)
        current_user.email_verification_expires = None

        # Reset any failed login attempts after successful password change
        current_user.failed_login_attempts = 0
        current_user.locked_until = None

        db.add(current_user)
        await db.commit()
        await db.refresh(current_user)

        return ChangePasswordResponse(
            success=True,
            message="Password changed successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to change password: {str(e)}"
        )
