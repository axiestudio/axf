import base64
import hashlib
import random
import warnings
from collections.abc import Coroutine
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Annotated
from uuid import UUID

from cryptography.fernet import Fernet
from fastapi import Depends, HTTPException, Request, Security, WebSocketException, status
from fastapi.security import APIKeyHeader, APIKeyQuery, OAuth2PasswordBearer
from jose import JWTError, jwt
from axiestudio.logging import logger
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.websockets import WebSocket

from axiestudio.services.database.models.api_key.crud import check_key
from axiestudio.services.database.models.user.crud import get_user_by_id, get_user_by_username, update_user_last_login_at
from axiestudio.services.database.models.user.model import User, UserRead
from axiestudio.services.deps import get_db_service, get_session, get_settings_service
from axiestudio.services.settings.service import SettingsService

if TYPE_CHECKING:
    from axiestudio.services.database.models.api_key.model import ApiKey

oauth2_login = OAuth2PasswordBearer(tokenUrl="api/v1/login", auto_error=False)

API_KEY_NAME = "x-api-key"

api_key_query = APIKeyQuery(name=API_KEY_NAME, scheme_name="API key query", auto_error=False)
api_key_header = APIKeyHeader(name=API_KEY_NAME, scheme_name="API key header", auto_error=False)

MINIMUM_KEY_LENGTH = 32
AUTO_LOGIN_WARNING = "In v1.6 AXIESTUDIO_SKIP_AUTH_AUTO_LOGIN will be removed. Please update your authentication method."
AUTO_LOGIN_ERROR = (
    "Since v1.5, AXIESTUDIO_AUTO_LOGIN requires a valid API key. "
    "Set AXIESTUDIO_SKIP_AUTH_AUTO_LOGIN=true to skip this check. "
    "Please update your authentication method."
)


# Import centralized timezone utility
from axiestudio.utils.timezone import ensure_timezone_aware


# Source: https://github.com/mrtolkien/fastapi_simple_security/blob/master/fastapi_simple_security/security_api_key.py
async def api_key_security(
    query_param: Annotated[str, Security(api_key_query)],
    header_param: Annotated[str, Security(api_key_header)],
) -> UserRead | None:
    settings_service = get_settings_service()
    result: ApiKey | User | None

    async with get_db_service().with_session() as db:
        if settings_service.auth_settings.AUTO_LOGIN:
            # Get the first user
            if not settings_service.auth_settings.SUPERUSER:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Missing first superuser credentials",
                )
            if not query_param and not header_param:
                if settings_service.auth_settings.skip_auth_auto_login:
                    result = await get_user_by_username(db, settings_service.auth_settings.SUPERUSER)
                    logger.warning(AUTO_LOGIN_WARNING)
                    return UserRead.model_validate(result, from_attributes=True)
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=AUTO_LOGIN_ERROR,
                )
            result = await check_key(db, query_param or header_param)

        elif not query_param and not header_param:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="An API key must be passed as query or header",
            )

        else:
            result = await check_key(db, query_param or header_param)

        if not result:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid or missing API key",
            )

        if isinstance(result, User):
            return UserRead.model_validate(result, from_attributes=True)

    msg = "Invalid result type"
    raise ValueError(msg)


async def ws_api_key_security(
    api_key: str | None,
) -> UserRead:
    settings = get_settings_service()
    async with get_db_service().with_session() as db:
        if settings.auth_settings.AUTO_LOGIN:
            if not settings.auth_settings.SUPERUSER:
                # internal server misconfiguration
                raise WebSocketException(
                    code=status.WS_1011_INTERNAL_ERROR,
                    reason="Missing first superuser credentials",
                )
            if not api_key:
                if settings.auth_settings.skip_auth_auto_login:
                    result = await get_user_by_username(db, settings.auth_settings.SUPERUSER)
                    logger.warning(AUTO_LOGIN_WARNING)
                else:
                    raise WebSocketException(
                        code=status.WS_1008_POLICY_VIOLATION,
                        reason=AUTO_LOGIN_ERROR,
                    )
            else:
                result = await check_key(db, api_key)

        # normal path: must provide an API key
        else:
            if not api_key:
                raise WebSocketException(
                    code=status.WS_1008_POLICY_VIOLATION,
                    reason="An API key must be passed as query or header",
                )
            result = await check_key(db, api_key)

        # key was invalid or missing
        if not result:
            raise WebSocketException(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Invalid or missing API key",
            )

        # convert SQL-model User → pydantic UserRead
        if isinstance(result, User):
            return UserRead.model_validate(result, from_attributes=True)

    # fallback: something unexpected happened
    raise WebSocketException(
        code=status.WS_1011_INTERNAL_ERROR,
        reason="Authentication subsystem error",
    )


async def get_current_user(
    token: Annotated[str, Security(oauth2_login)],
    query_param: Annotated[str, Security(api_key_query)],
    header_param: Annotated[str, Security(api_key_header)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    if token:
        return await get_current_user_by_jwt(token, db)
    user = await api_key_security(query_param, header_param)
    if user:
        return user

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid or missing API key",
    )


async def get_current_user_by_jwt(
    token: str,
    db: AsyncSession,
) -> User:
    settings_service = get_settings_service()

    if isinstance(token, Coroutine):
        token = await token

    secret_key = settings_service.auth_settings.SECRET_KEY.get_secret_value()
    if secret_key is None:
        logger.error("Secret key is not set in settings.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            # Careful not to leak sensitive information
            detail="Authentication failure: Verify authentication settings.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            payload = jwt.decode(token, secret_key, algorithms=[settings_service.auth_settings.ALGORITHM])
        user_id: UUID = payload.get("sub")  # type: ignore[assignment]
        token_type: str = payload.get("type")  # type: ignore[assignment]
        if expires := payload.get("exp", None):
            expires_datetime = datetime.fromtimestamp(expires, timezone.utc)
            if datetime.now(timezone.utc) > expires_datetime:
                logger.info("Token expired for user")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token has expired.",
                    headers={"WWW-Authenticate": "Bearer"},
                )

        if user_id is None or token_type is None:
            logger.info(f"Invalid token payload. Token type: {token_type}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token details.",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except JWTError as e:
        logger.debug("JWT validation failed: Invalid token format or signature")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    user = await get_user_by_id(db, user_id)
    if user is None or not user.is_active:
        logger.info("User not found or inactive.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or is inactive.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # CRITICAL FIX: Force refresh user object from database to get latest subscription status
    # This prevents stale data issues when webhooks update subscription status
    await db.refresh(user)

    return user


async def get_current_user_for_websocket(
    websocket: WebSocket,
    db: AsyncSession,
) -> User | UserRead:
    token = websocket.cookies.get("access_token_as") or websocket.query_params.get("token")
    if token:
        user = await get_current_user_by_jwt(token, db)
        if user:
            return user

    api_key = (
        websocket.query_params.get("x-api-key")
        or websocket.query_params.get("api_key")
        or websocket.headers.get("x-api-key")
        or websocket.headers.get("api_key")
    )
    if api_key:
        user_read = await ws_api_key_security(api_key)
        if user_read:
            return user_read

    raise WebSocketException(
        code=status.WS_1008_POLICY_VIOLATION, reason="Missing or invalid credentials (cookie, token or API key)."
    )


async def get_current_active_user(current_user: Annotated[User, Depends(get_current_user)]):
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")
    return current_user


async def get_current_active_superuser(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")
    if not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="The user doesn't have enough privileges")
    return current_user


async def get_webhook_user(flow_id: str, request: Request) -> UserRead:
    """Get the user for webhook execution.

    When WEBHOOK_AUTH_ENABLE=false, allows execution as the flow owner without API key.
    When WEBHOOK_AUTH_ENABLE=true, requires API key authentication and validates flow ownership.

    Args:
        flow_id: The ID of the flow being executed
        request: The FastAPI request object

    Returns:
        UserRead: The user to execute the webhook as

    Raises:
        HTTPException: If authentication fails or user doesn't have permission
    """
    from axiestudio.helpers.user import get_user_by_flow_id_or_endpoint_name

    settings_service = get_settings_service()

    if not getattr(settings_service.auth_settings, 'WEBHOOK_AUTH_ENABLE', True):
        # When webhook auth is disabled, run webhook as the flow owner without requiring API key
        try:
            flow_owner = await get_user_by_flow_id_or_endpoint_name(flow_id)
            if flow_owner is None:
                raise HTTPException(status_code=404, detail="Flow not found")
            return flow_owner  # noqa: TRY300
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=404, detail="Flow not found") from exc

    # When webhook auth is enabled, require API key authentication
    api_key_header_val = request.headers.get("x-api-key")
    api_key_query_val = request.query_params.get("x-api-key")

    # Check if API key is provided
    if not api_key_header_val and not api_key_query_val:
        raise HTTPException(status_code=403, detail="API key required when webhook authentication is enabled")

    # Use the provided API key (prefer header over query param)
    api_key = api_key_header_val or api_key_query_val

    try:
        # Validate API key directly without AUTO_LOGIN fallback
        async with get_db_service().with_session() as db:
            result = await check_key(db, api_key)
            if not result:
                logger.warning("Invalid API key provided for webhook")
                raise HTTPException(status_code=403, detail="Invalid API key")

            authenticated_user = UserRead.model_validate(result, from_attributes=True)
            logger.info("Webhook API key validated successfully")

            # Verify the authenticated user has access to the flow
            try:
                flow_owner = await get_user_by_flow_id_or_endpoint_name(flow_id)
                if flow_owner is None:
                    raise HTTPException(status_code=404, detail="Flow not found")

                # Allow access if user is superuser or flow owner
                if authenticated_user.is_superuser or authenticated_user.id == flow_owner.id:
                    return authenticated_user
                else:
                    raise HTTPException(status_code=403, detail="User does not have access to this flow")
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(status_code=404, detail="Flow not found") from exc

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as exc:
        # Handle other exceptions
        logger.error(f"Webhook API key validation error: {exc}")
        raise HTTPException(status_code=500, detail="Authentication error") from exc


def verify_password(plain_password, hashed_password):
    settings_service = get_settings_service()
    return settings_service.auth_settings.pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    settings_service = get_settings_service()
    return settings_service.auth_settings.pwd_context.hash(password)


def create_token(data: dict, expires_delta: timedelta):
    settings_service = get_settings_service()

    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode["exp"] = expire

    return jwt.encode(
        to_encode,
        settings_service.auth_settings.SECRET_KEY.get_secret_value(),
        algorithm=settings_service.auth_settings.ALGORITHM,
    )


async def create_super_user(
    username: str,
    password: str,
    db: AsyncSession,
) -> User:
    super_user = await get_user_by_username(db, username)

    if not super_user:
        # For superuser, use username as email if it contains @, otherwise create admin email
        admin_email = username if "@" in username else f"{username}@axiestudio.admin"

        super_user = User(
            username=username,
            email=admin_email,  # Required field for new User model
            password=get_password_hash(password),
            is_superuser=True,
            is_active=True,
            last_login_at=None,
        )

        db.add(super_user)
        try:
            await db.commit()
            await db.refresh(super_user)
        except IntegrityError:
            # Race condition - another worker created the user
            await db.rollback()
            super_user = await get_user_by_username(db, username)
            if not super_user:
                raise  # Re-raise if it's not a race condition
        except Exception:  # noqa: BLE001
            logger.opt(exception=True).debug("Error creating superuser.")

    return super_user


async def create_user_longterm_token(db: AsyncSession) -> tuple[UUID, dict]:
    settings_service = get_settings_service()

    username = settings_service.auth_settings.SUPERUSER
    super_user = await get_user_by_username(db, username)
    if not super_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Super user hasn't been created")
    access_token_expires_longterm = timedelta(days=365)
    access_token = create_token(
        data={"sub": str(super_user.id), "type": "access"},
        expires_delta=access_token_expires_longterm,
    )

    # Update: last_login_at
    await update_user_last_login_at(super_user.id, db)

    return super_user.id, {
        "access_token": access_token,
        "refresh_token": None,
        "token_type": "bearer",
    }


def create_user_api_key(user_id: UUID) -> dict:
    access_token = create_token(
        data={"sub": str(user_id), "type": "api_key"},
        expires_delta=timedelta(days=365 * 2),
    )

    return {"api_key": access_token}


def get_user_id_from_token(token: str) -> UUID:
    try:
        user_id = jwt.get_unverified_claims(token)["sub"]
        return UUID(user_id)
    except (KeyError, JWTError, ValueError):
        return UUID(int=0)


async def create_user_tokens(user_id: UUID, db: AsyncSession, *, update_last_login: bool = False) -> dict:
    settings_service = get_settings_service()

    access_token_expires = timedelta(seconds=settings_service.auth_settings.ACCESS_TOKEN_EXPIRE_SECONDS)
    access_token = create_token(
        data={"sub": str(user_id), "type": "access"},
        expires_delta=access_token_expires,
    )

    refresh_token_expires = timedelta(seconds=settings_service.auth_settings.REFRESH_TOKEN_EXPIRE_SECONDS)
    refresh_token = create_token(
        data={"sub": str(user_id), "type": "refresh"},
        expires_delta=refresh_token_expires,
    )

    # Update: last_login_at
    if update_last_login:
        await update_user_last_login_at(user_id, db)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


async def create_refresh_token(refresh_token: str, db: AsyncSession):
    settings_service = get_settings_service()

    try:
        # Ignore warning about datetime.utcnow
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            payload = jwt.decode(
                refresh_token,
                settings_service.auth_settings.SECRET_KEY.get_secret_value(),
                algorithms=[settings_service.auth_settings.ALGORITHM],
            )
        user_id: UUID = payload.get("sub")  # type: ignore[assignment]
        token_type: str = payload.get("type")  # type: ignore[assignment]

        if user_id is None or token_type == "":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

        user_exists = await get_user_by_id(db, user_id)

        if user_exists is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

        return await create_user_tokens(user_id, db)

    except JWTError as e:
        logger.exception("JWT decoding error")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        ) from e


async def authenticate_user(username: str, password: str, db: AsyncSession, client_ip: str = "unknown", user_agent: str = "unknown") -> User | None:
    """Enhanced authentication with enterprise security features."""
    from axiestudio.logging import logger

    user = await get_user_by_username(db, username)

    if not user:
        # Log failed login attempt for non-existent user
        logger.warning(f"Login attempt for non-existent user: {username} from IP: {client_ip}")
        return None

    # Check if account is locked
    if user.locked_until:
        # Ensure both datetimes are timezone-aware for proper comparison
        locked_until_aware = ensure_timezone_aware(user.locked_until)
        now = datetime.now(timezone.utc)

        if locked_until_aware and locked_until_aware > now:
            time_remaining = locked_until_aware - now
        logger.warning(f"Login attempt for locked account: {username} from IP: {client_ip}")
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"Account is temporarily locked. Try again in {int(time_remaining.total_seconds() / 60)} minutes."
        )

    if not user.is_active:
        if not user.email_verified:
            logger.info(f"Login attempt for unverified user: {username} from IP: {client_ip}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Please verify your email address before logging in. Check your inbox for the verification link."
            )
        if not user.last_login_at:
            logger.info(f"Login attempt for pending user: {username} from IP: {client_ip}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Account pending approval")
        logger.warning(f"Login attempt for inactive user: {username} from IP: {client_ip}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account is inactive")

    # Verify password
    if verify_password(password, user.password):
        # Check if this is a temporary password that has expired
        if user.password_changed_at is None and user.email_verification_expires:
            now = datetime.now(timezone.utc)

            # Ensure both datetimes are timezone-aware for proper comparison
            expiry_time = ensure_timezone_aware(user.email_verification_expires)

            if expiry_time and expiry_time < now:
                # Temporary password has expired
                logger.warning(f"Temporary password expired for user: {username} from IP: {client_ip}")
                user.failed_login_attempts += 1
                user.last_failed_login = now
                await db.commit()
                raise HTTPException(
                    status_code=401,
                    detail="Temporary password has expired. Please request a new password reset."
                )

        # Successful login - reset failed attempts and update login info
        user.failed_login_attempts = 0
        user.last_failed_login = None
        user.locked_until = None
        user.last_login_ip = client_ip
        user.login_attempts += 1

        # Check if user needs to change password (temporary password scenario)
        if user.password_changed_at is None:
            logger.info(f"User {username} logged in with temporary password, requires password change")
            # We'll handle this in the login endpoint by returning a special flag

        logger.info(f"Successful login for user: {username} from IP: {client_ip}")
        await db.commit()

        # 🔔 NEW: Track login and send security notification if needed
        try:
            from axiestudio.services.security.login_detection import get_login_detection_service
            login_detection = get_login_detection_service()

            # Track this login asynchronously (don't block the login process)
            import asyncio
            asyncio.create_task(
                login_detection.track_login(db, user, client_ip, user_agent)
            )
        except Exception as e:
            logger.error(f"Error tracking login for security notification: {e}")
            # Don't fail the login if notification fails

        return user
    else:
        # Failed login - increment failed attempts
        user.failed_login_attempts += 1
        user.last_failed_login = datetime.now(timezone.utc)

        # Lock account after 5 failed attempts
        if user.failed_login_attempts >= 5:
            user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=30)
            logger.warning(f"Account locked for user: {username} after 5 failed attempts from IP: {client_ip}")
        else:
            logger.warning(f"Failed login attempt {user.failed_login_attempts}/5 for user: {username} from IP: {client_ip}")

        await db.commit()
        return None


def add_padding(s):
    # Calculate the number of padding characters needed
    padding_needed = 4 - len(s) % 4
    return s + "=" * padding_needed


def add_padding(s):
    # Calculate the number of padding characters needed
    padding_needed = 4 - len(s) % 4
    return s + "=" * padding_needed


def ensure_valid_key(s: str) -> bytes:
    # If the key is too short, we'll use it as a seed to generate a valid key
    if len(s) < MINIMUM_KEY_LENGTH:
        # Use the input as a seed for the random number generator
        random.seed(s)
        # Generate 32 random bytes
        key = bytes(random.getrandbits(8) for _ in range(32))
        key = base64.urlsafe_b64encode(key)
    else:
        # For longer keys, try to use them as base64 or create a valid key from them
        try:
            # First, try to decode as base64 to check if it's already a valid key
            decoded = base64.urlsafe_b64decode(add_padding(s))
            if len(decoded) == 32:
                # It's already a valid 32-byte key
                key = add_padding(s).encode()
            else:
                # Not 32 bytes, so create a valid key from the input
                key = base64.urlsafe_b64encode(hashlib.sha256(s.encode()).digest())
        except Exception:
            # If base64 decoding fails, create a valid key from the input
            key = base64.urlsafe_b64encode(hashlib.sha256(s.encode()).digest())
    return key


def get_fernet(settings_service: SettingsService):
    secret_key: str = settings_service.auth_settings.SECRET_KEY.get_secret_value()
    valid_key = ensure_valid_key(secret_key)
    return Fernet(valid_key)


def encrypt_api_key(api_key: str, settings_service: SettingsService):
    fernet = get_fernet(settings_service)
    # Two-way encryption
    encrypted_key = fernet.encrypt(api_key.encode())
    return encrypted_key.decode()


def decrypt_api_key(encrypted_api_key: str, settings_service: SettingsService):
    """Decrypt the provided encrypted API key using Fernet decryption.

    This function first attempts to decrypt the API key by encoding it,
    assuming it is a properly encoded string. If that fails, it logs a detailed
    debug message including the exception information and retries decryption
    using the original string input.

    Args:
        encrypted_api_key (str): The encrypted API key.
        settings_service (SettingsService): Service providing authentication settings.

    Returns:
        str: The decrypted API key, or an empty string if decryption cannot be performed.
    """
    fernet = get_fernet(settings_service)
    if isinstance(encrypted_api_key, str):
        try:
            return fernet.decrypt(encrypted_api_key.encode()).decode()
        except Exception as primary_exception:  # noqa: BLE001
            logger.debug(
                "Decryption using UTF-8 encoded API key failed. Error: %s. "
                "Retrying decryption using the raw string input.",
                primary_exception,
            )
            return fernet.decrypt(encrypted_api_key).decode()
    return ""


# MCP-specific authentication functions that always behave as if skip_auth_auto_login is True
async def get_current_user_mcp(
    token: Annotated[str, Security(oauth2_login)],
    query_param: Annotated[str, Security(api_key_query)],
    header_param: Annotated[str, Security(api_key_header)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    """MCP-specific user authentication that always allows fallback to username lookup.

    This function provides authentication for MCP endpoints with special handling:
    - If a JWT token is provided, it uses standard JWT authentication
    - If no API key is provided and AUTO_LOGIN is enabled, it falls back to
      username lookup using the configured superuser credentials
    - Otherwise, it validates the provided API key (from query param or header)
    """
    if token:
        return await get_current_user_by_jwt(token, db)

    # MCP-specific authentication logic - always behaves as if skip_auth_auto_login is True
    settings_service = get_settings_service()
    result: ApiKey | User | None

    if settings_service.auth_settings.AUTO_LOGIN:
        # Get the first user
        if not settings_service.auth_settings.SUPERUSER:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing first superuser credentials",
            )
        if not query_param and not header_param:
            # For MCP endpoints, always fall back to username lookup when no API key is provided
            result = await get_user_by_username(db, settings_service.auth_settings.SUPERUSER)
            if result:
                logger.warning(AUTO_LOGIN_WARNING)
                return result
        else:
            result = await check_key(db, query_param or header_param)

    elif not query_param and not header_param:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="An API key must be passed as query or header",
        )

    elif query_param:
        result = await check_key(db, query_param)

    else:
        result = await check_key(db, header_param)

    if not result:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API key",
        )

    # If result is a User, return it directly
    if isinstance(result, User):
        return result

    # If result is an ApiKey, we need to get the associated user
    # This should not happen in normal flow, but adding for completeness
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid authentication result",
    )


async def get_current_active_user_mcp(current_user: Annotated[User, Depends(get_current_user_mcp)]):
    """MCP-specific active user dependency.

    This dependency is temporary and will be removed once MCP is fully integrated.
    """
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")
    return current_user
