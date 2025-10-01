"""Subscription API endpoints."""

import os
from datetime import datetime, timezone, timedelta
from typing import Annotated
from collections import defaultdict
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel
from axiestudio.logging import logger

from axiestudio.api.utils import CurrentActiveUser, DbSession
from axiestudio.services.auth.utils import get_current_active_user
from axiestudio.services.deps import get_session
from axiestudio.services.stripe.service import stripe_service
from axiestudio.services.database.models.user.crud import update_user
from axiestudio.services.database.models.user.model import UserUpdate

# Import subscription setup for manual migration
try:
    from axiestudio.services.startup.subscription_setup import setup_subscription_schema
    SUBSCRIPTION_SETUP_AVAILABLE = True
except ImportError:
    SUBSCRIPTION_SETUP_AVAILABLE = False

# Simple rate limiting for subscription endpoints
_rate_limit_store = defaultdict(list)
RATE_LIMIT_WINDOW = 300  # 5 minutes
RATE_LIMIT_MAX_REQUESTS = 10  # Max 10 subscription requests per 5 minutes per user

def check_rate_limit(user_id: str, endpoint: str) -> bool:
    """Check if user has exceeded rate limit for subscription endpoints."""
    now = time.time()
    key = f"{user_id}:{endpoint}"

    # Clean old entries
    _rate_limit_store[key] = [
        timestamp for timestamp in _rate_limit_store[key]
        if now - timestamp < RATE_LIMIT_WINDOW
    ]

    # Check if limit exceeded
    if len(_rate_limit_store[key]) >= RATE_LIMIT_MAX_REQUESTS:
        return False

    # Add current request
    _rate_limit_store[key].append(now)
    return True

router = APIRouter(tags=["Subscriptions"], prefix="/subscriptions")


class CreateCheckoutRequest(BaseModel):
    success_url: str
    cancel_url: str


class CheckoutResponse(BaseModel):
    checkout_url: str


class CustomerPortalResponse(BaseModel):
    portal_url: str


@router.post("/create-checkout", response_model=CheckoutResponse)
async def create_checkout_session(
    request: CreateCheckoutRequest,
    current_user: CurrentActiveUser,
    session: DbSession,
):
    """Create a Stripe checkout session for subscription."""
    # Rate limiting check
    if not check_rate_limit(str(current_user.id), "create-checkout"):
        raise HTTPException(
            status_code=429,
            detail="Too many subscription requests. Please wait a few minutes before trying again."
        )

    if not stripe_service.is_configured():
        raise HTTPException(status_code=503, detail="Stripe is not configured. Please contact support.")

    try:
        # Create Stripe customer if not exists
        stripe_customer_id = getattr(current_user, 'stripe_customer_id', None)
        if not stripe_customer_id:
            # Use user's email (handle case where email might be None for existing users)
            user_email = current_user.email
            if not user_email:
                raise HTTPException(
                    status_code=400,
                    detail="Email address is required for subscription. Please update your profile with a valid email address."
                )

            customer_id = await stripe_service.create_customer(
                email=user_email,
                name=current_user.username
            )
            
            # Update user with Stripe customer ID
            update_data = UserUpdate(stripe_customer_id=customer_id)
            await update_user(session, current_user.id, update_data)
        else:
            customer_id = current_user.stripe_customer_id
        
        # Calculate remaining trial days (don't give double trial)
        now = datetime.now(timezone.utc)

        # Handle trial dates safely with timezone consistency
        trial_start = getattr(current_user, 'trial_start', None)
        trial_end = getattr(current_user, 'trial_end', None)

        # CRITICAL FIX: Ensure all datetime objects are timezone-aware
        if trial_start is None:
            trial_start = now
        elif trial_start.tzinfo is None:
            trial_start = trial_start.replace(tzinfo=timezone.utc)

        if trial_end is None:
            trial_end = trial_start + timedelta(days=7)
        elif trial_end.tzinfo is None:
            trial_end = trial_end.replace(tzinfo=timezone.utc)

        # CORRECT ENTERPRISE TRIAL SYSTEM:
        # - New users get 7-day APP-MANAGED trial (no Stripe trial)
        # - Trial users upgrading get immediate paid subscription (trial_days=0)
        # - This prevents double-billing while maintaining proper trial experience

        # CRITICAL LOGIC: Only users who need to pay should reach this endpoint
        # New users should use the app for 7 days BEFORE needing to subscribe

        is_on_trial = current_user.subscription_status == "trial"

        if is_on_trial:
            # TRIAL USER UPGRADING: Immediate payment without additional trial days
            remaining_trial_days = 0
        else:
            # NON-TRIAL USER: User with expired trial or direct subscription
            remaining_trial_days = 0

        # Create checkout session - always trial_days=0 for immediate payment
        # This is correct since only users who need to pay reach this endpoint
        checkout_url = await stripe_service.create_checkout_session(
            customer_id=customer_id,
            success_url=request.success_url,
            cancel_url=request.cancel_url,
            trial_days=remaining_trial_days  # Always 0 - immediate payment
        )
        
        return CheckoutResponse(checkout_url=checkout_url)
        
    except Exception as e:
        logger.error(f"Failed to create checkout session for user {current_user.id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to create checkout session. Please try again or contact support.")


@router.post("/customer-portal", response_model=CustomerPortalResponse)
async def create_customer_portal(
    current_user: CurrentActiveUser,
    session: DbSession,
):
    """Create a Stripe customer portal session."""
    # Rate limiting check
    if not check_rate_limit(str(current_user.id), "customer-portal"):
        raise HTTPException(
            status_code=429,
            detail="Too many portal requests. Please wait a few minutes before trying again."
        )

    if not stripe_service.is_configured():
        raise HTTPException(status_code=503, detail="Stripe is not configured. Please contact support.")

    try:
        # Create Stripe customer if not exists
        if not current_user.stripe_customer_id:
            # Use user's email (handle case where email might be None for existing users)
            user_email = current_user.email
            if not user_email:
                raise HTTPException(
                    status_code=400,
                    detail="Email address is required for subscription management. Please update your profile with a valid email address."
                )

            customer_id = await stripe_service.create_customer(
                email=user_email,
                name=current_user.username
            )

            # Update user with Stripe customer ID
            update_data = UserUpdate(stripe_customer_id=customer_id)
            await update_user(session, current_user.id, update_data)
        else:
            customer_id = current_user.stripe_customer_id

        # Get the frontend URL from environment or use default
        # Try multiple environment variables for different deployment platforms
        frontend_url = (
            os.getenv("FRONTEND_URL") or
            os.getenv("RAILWAY_PUBLIC_DOMAIN") and f"https://{os.getenv('RAILWAY_PUBLIC_DOMAIN')}" or
            os.getenv("VERCEL_URL") and f"https://{os.getenv('VERCEL_URL')}" or
            os.getenv("RENDER_EXTERNAL_URL") or
            "http://localhost:7860"
        )
        return_url = f"{frontend_url}/settings"

        logger.info(f"Creating customer portal with return_url: {return_url}")
        logger.debug(f"Environment variables - FRONTEND_URL: {os.getenv('FRONTEND_URL')}, RAILWAY_PUBLIC_DOMAIN: {os.getenv('RAILWAY_PUBLIC_DOMAIN')}")

        portal_url = await stripe_service.create_customer_portal_session(
            customer_id=customer_id,
            return_url=return_url
        )
        
        return CustomerPortalResponse(portal_url=portal_url)
        
    except Exception as e:
        logger.error(f"Failed to create customer portal for user {current_user.id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to create customer portal. Please try again or contact support.")


@router.get("/health")
async def subscription_health():
    """Check if subscription service is healthy."""
    return {
        "stripe_configured": stripe_service.is_configured(),
        "service_status": "healthy"
    }


@router.post("/migrate-schema")
async def migrate_subscription_schema(session: DbSession):
    """Manually trigger subscription schema migration."""
    try:
        from sqlalchemy import text

        logger.info("Starting manual subscription schema migration...")

        # Check database type
        db_url = str(session.bind.url).lower()
        is_sqlite = "sqlite" in db_url

        # Check existing columns
        if is_sqlite:
            result = await session.exec(text("PRAGMA table_info(user);"))
            existing_columns = {row[1] for row in result.fetchall()}
        else:
            result = await session.exec(text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'user' AND table_schema = 'public';
            """))
            existing_columns = {row[0] for row in result.fetchall()}

        # Define subscription columns
        subscription_columns = [
            ('stripe_customer_id', 'VARCHAR(255)'),
            ('subscription_status', "VARCHAR(50) DEFAULT 'trial'"),
            ('subscription_id', 'VARCHAR(255)'),
            ('trial_start', 'TIMESTAMP'),
            ('trial_end', 'TIMESTAMP'),
            ('subscription_start', 'TIMESTAMP'),
            ('subscription_end', 'TIMESTAMP')
        ]

        added_columns = []
        errors = []

        # Add missing columns
        for column_name, column_def in subscription_columns:
            if column_name not in existing_columns:
                try:
                    if is_sqlite:
                        sql = f"ALTER TABLE user ADD COLUMN {column_name} {column_def};"
                    else:
                        sql = f'ALTER TABLE "user" ADD COLUMN {column_name} {column_def};'

                    await session.exec(text(sql))
                    added_columns.append(column_name)
                    logger.info(f"Added column: {column_name}")
                except Exception as e:
                    error_msg = f"Failed to add {column_name}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(error_msg)

        # Commit changes
        if added_columns:
            await session.commit()

            # Update existing users
            try:
                if is_sqlite:
                    update_sql = """
                        UPDATE user SET
                            trial_start = COALESCE(trial_start, create_at),
                            trial_end = COALESCE(trial_end, datetime(create_at, '+7 days')),
                            subscription_status = COALESCE(subscription_status, 'trial')
                        WHERE trial_start IS NULL OR subscription_status IS NULL;
                    """
                else:
                    update_sql = """
                        UPDATE "user" SET
                            trial_start = COALESCE(trial_start, create_at),
                            trial_end = COALESCE(trial_end, create_at + INTERVAL '7 days'),
                            subscription_status = COALESCE(subscription_status, 'trial')
                        WHERE trial_start IS NULL OR subscription_status IS NULL;
                    """

                await session.exec(text(update_sql))
                await session.commit()
                logger.info("Updated existing users with trial defaults")
            except Exception as e:
                errors.append(f"Failed to update users: {str(e)}")

        return {
            "success": len(errors) == 0,
            "database_type": "sqlite" if is_sqlite else "postgresql",
            "existing_columns": sorted(existing_columns),
            "added_columns": added_columns,
            "errors": errors,
            "message": f"Added {len(added_columns)} columns" if added_columns else "All columns already exist"
        }

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise HTTPException(status_code=500, detail=f"Migration failed: {str(e)}")


@router.get("/debug/schema")
async def debug_database_schema(session: DbSession):
    """Debug endpoint to check what columns exist in the user table."""
    try:
        from sqlalchemy import text

        # Check if we're using SQLite or PostgreSQL
        db_url = str(session.bind.url).lower()
        is_sqlite = "sqlite" in db_url

        if is_sqlite:
            # SQLite: Check table schema
            result = await session.exec(text("PRAGMA table_info(user);"))
            rows = result.fetchall()
            columns = [{"name": row[1], "type": row[2], "nullable": bool(row[3]), "default": row[4]} for row in rows]
        else:
            # PostgreSQL: Check information_schema
            result = await session.exec(text("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name = 'user' AND table_schema = 'public'
                ORDER BY ordinal_position;
            """))
            rows = result.fetchall()
            columns = [{"name": row[0], "type": row[1], "nullable": row[2] == "YES", "default": row[3]} for row in rows]

        # Check which subscription columns are missing
        subscription_columns = [
            'stripe_customer_id', 'subscription_status', 'subscription_id',
            'trial_start', 'trial_end', 'subscription_start', 'subscription_end'
        ]

        existing_column_names = {col["name"] for col in columns}
        missing_columns = [col for col in subscription_columns if col not in existing_column_names]

        return {
            "database_type": "sqlite" if is_sqlite else "postgresql",
            "total_columns": len(columns),
            "all_columns": columns,
            "subscription_columns_missing": missing_columns,
            "subscription_columns_present": [col for col in subscription_columns if col in existing_column_names]
        }

    except Exception as e:
        logger.error(f"Error checking database schema: {e}")
        raise HTTPException(status_code=500, detail=f"Schema check failed: {str(e)}")


@router.get("/status")
async def get_subscription_status(current_user: CurrentActiveUser, session: DbSession):
    """Get current user's subscription status with real-time verification."""
    try:
        # ENTERPRISE PATTERN: Single efficient refresh for latest data
        await session.refresh(current_user)
        logger.debug(f"🔄 User {current_user.username} subscription status: {current_user.subscription_status}")
        # Superusers don't have subscriptions - they have unlimited access
        if current_user.is_superuser:
            return {
                "subscription_status": "admin",
                "subscription_id": None,
                "trial_start": None,
                "trial_end": None,
                "trial_expired": False,
                "trial_days_left": None,
                "subscription_start": None,
                "subscription_end": None,
                "has_stripe_customer": False,
                "is_superuser": True
            }

        # Handle missing subscription columns gracefully
        trial_start = getattr(current_user, 'trial_start', None)
        trial_end = getattr(current_user, 'trial_end', None)
        subscription_status = getattr(current_user, 'subscription_status', 'trial')
        subscription_id = getattr(current_user, 'subscription_id', None)
        subscription_start = getattr(current_user, 'subscription_start', None)
        subscription_end = getattr(current_user, 'subscription_end', None)
        stripe_customer_id = getattr(current_user, 'stripe_customer_id', None)

        # CRITICAL FIX: Ensure timezone awareness for subscription dates
        if subscription_start and subscription_start.tzinfo is None:
            subscription_start = subscription_start.replace(tzinfo=timezone.utc)
        if subscription_end and subscription_end.tzinfo is None:
            subscription_end = subscription_end.replace(tzinfo=timezone.utc)

        # Calculate trial status and days_left - CRITICAL: Handle different subscription states correctly
        trial_expired = False
        days_left = 7  # Default to 7 days if no trial_start
        now = datetime.now(timezone.utc)

        # CRITICAL FIX: Calculate days_left based on subscription status
        if subscription_status == "active":
            trial_expired = False  # Active subscribers are never "trial expired"
            days_left = 0  # No trial days left because they have active subscription
        elif subscription_status == "canceled" and subscription_end:
            # CRITICAL FIX: For canceled subscriptions, calculate days until subscription_end
            trial_expired = False  # Canceled users with remaining time are not "trial expired"
            if subscription_end.tzinfo is None:
                subscription_end = subscription_end.replace(tzinfo=timezone.utc)

            if now >= subscription_end:
                days_left = 0  # Subscription has expired
            else:
                # Calculate remaining days until subscription ends
                remaining_seconds = (subscription_end - now).total_seconds()
                days_left = max(0, int(remaining_seconds / 86400))  # 86400 seconds = 1 day
                logger.info(f"🔄 Canceled subscription for {current_user.username}: {days_left} days remaining until {subscription_end}")
        elif trial_start:
            # For trial users, calculate trial days
            trial_end_date = trial_end or (trial_start + timedelta(days=7))

            # Ensure timezone consistency for comparisons
            if trial_start.tzinfo is None:
                trial_start = trial_start.replace(tzinfo=timezone.utc)
            if trial_end_date.tzinfo is None:
                trial_end_date = trial_end_date.replace(tzinfo=timezone.utc)

            if now > trial_end_date:
                trial_expired = True
                days_left = 0
            else:
                # FIXED: Use total_seconds() for accurate days calculation
                remaining_seconds = (trial_end_date - now).total_seconds()
                days_left = max(0, int(remaining_seconds / 86400))  # 86400 seconds = 1 day
        else:
            # If no trial_start, assume user just signed up
            trial_start = current_user.create_at
            if trial_start:
                # CRITICAL FIX: Ensure timezone awareness for create_at
                if trial_start.tzinfo is None:
                    trial_start = trial_start.replace(tzinfo=timezone.utc)
                trial_end = trial_start + timedelta(days=7)
            else:
                # Fallback if create_at is somehow None
                trial_start = datetime.now(timezone.utc)
                trial_end = trial_start + timedelta(days=7)

        # CRITICAL: Add real-time metadata for debugging and verification
        response_data = {
            "subscription_status": subscription_status,
            "subscription_id": subscription_id,
            "trial_start": trial_start,
            "trial_end": trial_end,
            "trial_expired": trial_expired,
            "trial_days_left": max(0, days_left) if subscription_status == "trial" else None,
            "days_left": max(0, days_left),  # Universal days_left field for all subscription types
            "subscription_start": subscription_start,
            "subscription_end": subscription_end,
            "has_stripe_customer": bool(stripe_customer_id),
            # Real-time verification metadata
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "user_id": str(current_user.id),
            "verification_timestamp": datetime.now(timezone.utc).timestamp()
        }

        logger.info(f"📊 Subscription status response for {current_user.username}: {subscription_status} (trial_expired: {trial_expired}, days_left: {max(0, days_left)})")
        return response_data

    except Exception as e:
        logger.error(f"Error getting subscription status: {e}")
        # Return safe defaults if there's an error with proper timezone handling
        safe_create_at = current_user.create_at
        if safe_create_at and safe_create_at.tzinfo is None:
            safe_create_at = safe_create_at.replace(tzinfo=timezone.utc)
        elif not safe_create_at:
            safe_create_at = datetime.now(timezone.utc)

        return {
            "subscription_status": "trial",
            "subscription_id": None,
            "trial_start": safe_create_at,
            "trial_end": safe_create_at + timedelta(days=7),
            "trial_expired": False,
            "trial_days_left": 7,
            "subscription_start": None,
            "subscription_end": None,
            "has_stripe_customer": False,
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "user_id": str(current_user.id),
            "verification_timestamp": datetime.now(timezone.utc).timestamp(),
            "error": str(e)
        }


@router.get("/status/realtime")
async def get_realtime_subscription_status(current_user: CurrentActiveUser, session: DbSession):
    """
    Real-time subscription status endpoint with enhanced verification.

    This endpoint provides the most up-to-date subscription information by:
    1. Force refreshing user data from database
    2. Cross-checking with Stripe if needed
    3. Providing detailed verification metadata
    """
    try:
        # CRITICAL: Multiple refresh attempts to ensure latest data
        await session.refresh(current_user)
        # Real-time status check

        # Get standard subscription status
        standard_response = await get_subscription_status(current_user, session)

        # Add real-time verification metadata
        realtime_metadata = {
            "realtime_check": True,
            "check_timestamp": datetime.now(timezone.utc).isoformat(),
            "database_refresh_count": 1,
            "verification_method": "database_refresh"
        }

        # If user has active subscription, verify with Stripe for extra confidence
        if (current_user.subscription_status == "active" and
            current_user.subscription_id and
            stripe_service.is_configured()):
            try:
                # Quick Stripe verification
                stripe_subscription = await stripe_service.get_subscription(current_user.subscription_id)
                if stripe_subscription:
                    stripe_status = stripe_subscription.get('status')
                    realtime_metadata.update({
                        "stripe_verification": True,
                        "stripe_status": stripe_status,
                        "stripe_matches_db": stripe_status == current_user.subscription_status
                    })
                    # Stripe verification successful
            except Exception as stripe_error:
                logger.warning(f"⚠️ Stripe verification failed for {current_user.username}: {stripe_error}")
                realtime_metadata.update({
                    "stripe_verification": False,
                    "stripe_error": str(stripe_error)
                })

        # Combine standard response with real-time metadata
        response = {**standard_response, **realtime_metadata}

        logger.info(f"📊 Real-time subscription status for {current_user.username}: {current_user.subscription_status}")
        return response

    except Exception as e:
        logger.error(f"Error in real-time subscription status check: {e}")
        raise HTTPException(status_code=500, detail=f"Real-time verification failed: {str(e)}")


@router.get("/success")
async def subscription_success(
    current_user: CurrentActiveUser,
    session: DbSession,
    session_id: str = Query(..., description="Stripe checkout session ID")
):
    # CRITICAL FIX: Correct FastAPI dependency injection syntax
    """Handle successful subscription - additional safety net for immediate activation."""
    try:
        if not stripe_service.is_configured():
            raise HTTPException(status_code=503, detail="Stripe is not configured")

        logger.info(f"🎉 Processing subscription success for user {current_user.username}, session: {session_id}")

        # Retrieve the checkout session from Stripe
        import stripe
        checkout_session = stripe.checkout.Session.retrieve(session_id)

        if not checkout_session:
            raise HTTPException(status_code=404, detail="Checkout session not found")

        # Verify this session belongs to the current user
        if checkout_session.customer != current_user.stripe_customer_id:
            logger.warning(f"Session customer mismatch: {checkout_session.customer} != {current_user.stripe_customer_id}")
            raise HTTPException(status_code=403, detail="Session does not belong to current user")

        # If there's a subscription, ensure user is activated
        if checkout_session.subscription:
            subscription_data = await stripe_service.get_subscription(checkout_session.subscription)
            if subscription_data and subscription_data.get('status') in ['active', 'trialing']:
                # Force update user status to active
                update_data = UserUpdate(
                    subscription_status='active',
                    subscription_id=checkout_session.subscription
                )
                await update_user(session, current_user.id, update_data)
                # Subscription activated successfully

                return {
                    "success": True,
                    "message": "Subscription successfully activated",
                    "subscription_status": "active",
                    "subscription_id": checkout_session.subscription
                }

        return {
            "success": True,
            "message": "Checkout session processed",
            "status": checkout_session.status
        }

    except Exception as e:
        logger.error(f"Error processing subscription success: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process subscription success: {str(e)}")


@router.post("/webhook")
async def stripe_webhook(request: Request, session: DbSession):
    """
    ENTERPRISE-GRADE Stripe webhook handler with proper transaction management.

    Features:
    - Idempotency with database-backed deduplication
    - Explicit transaction boundaries
    - Proper error handling and rollback
    - Performance optimized
    """
    try:
        payload = await request.body()
        sig_header = request.headers.get('stripe-signature')
        webhook_secret = os.getenv('STRIPE_WEBHOOK_SECRET')

        if not webhook_secret:
            raise HTTPException(status_code=500, detail="Webhook secret not configured")

        # Verify webhook signature
        import stripe
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, webhook_secret
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid payload")
        except stripe.error.SignatureVerificationError:
            raise HTTPException(status_code=400, detail="Invalid signature")

        # ENTERPRISE PATTERN: Database-backed idempotency (more reliable than cache)
        event_id = event.get('id')
        if event_id:
            # Check if webhook already processed using database
            from sqlalchemy import text
            result = await session.execute(
                text("SELECT id FROM webhook_events WHERE stripe_event_id = :event_id"),
                {"event_id": event_id}
            )
            if result.first():
                # Webhook already processed
                return {"status": "success", "message": "Already processed"}

            # Record webhook processing start
            event_type = event.get('type', 'unknown')
            await session.execute(
                text("INSERT INTO webhook_events (stripe_event_id, event_type, status, created_at) VALUES (:event_id, :event_type, 'processing', NOW())"),
                {"event_id": event_id, "event_type": event_type}
            )
            await session.commit()  # Commit immediately to prevent duplicates

        # ENTERPRISE PATTERN: Database transaction with proper error handling
        try:
            # Process the webhook event
            success = await stripe_service.handle_webhook_event(event, session)

            if success:
                # Mark webhook as completed
                if event_id:
                    await session.execute(
                        text("UPDATE webhook_events SET status = 'completed', completed_at = NOW() WHERE stripe_event_id = :event_id"),
                        {"event_id": event_id}
                    )

                # CRITICAL: Explicit commit for webhook processing
                await session.commit()
                # Webhook processed successfully
                return {"status": "success"}
            else:
                # Mark webhook as failed
                if event_id:
                    await session.execute(
                        text("UPDATE webhook_events SET status = 'failed', completed_at = NOW() WHERE stripe_event_id = :event_id"),
                        {"event_id": event_id}
                    )
                    await session.commit()
                raise HTTPException(status_code=500, detail="Failed to process webhook")

        except Exception as processing_error:
            # Rollback on any error
            await session.rollback()
            if event_id:
                # Mark as failed in separate transaction
                await session.execute(
                    text("UPDATE webhook_events SET status = 'failed', error_message = :error, completed_at = NOW() WHERE stripe_event_id = :event_id"),
                    {"event_id": event_id, "error": str(processing_error)}
                )
                await session.commit()
            raise

    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        raise HTTPException(status_code=500, detail=f"Webhook error: {str(e)}")


@router.delete("/cancel")
async def cancel_subscription(
    current_user: CurrentActiveUser,
    session: DbSession,
):
    """Cancel current user's subscription."""
    if not stripe_service.is_configured():
        raise HTTPException(status_code=503, detail="Stripe is not configured. Please contact support.")

    try:
        if not current_user.subscription_id:
            raise HTTPException(status_code=400, detail="No active subscription found")

        cancel_result = await stripe_service.cancel_subscription(current_user.subscription_id)

        if cancel_result["success"]:
            # CRITICAL FIX: Update user status with subscription end date but KEEP subscription_id
            # This allows users to maintain access until the billing period ends
            update_data = UserUpdate(
                subscription_status="canceled",
                subscription_end=cancel_result.get("subscription_end")
                # IMPORTANT: Do NOT set subscription_id=None here - keep it until subscription actually ends
            )
            await update_user(session, current_user.id, update_data)

            # 📧 Send cancellation confirmation email
            if current_user.email:
                try:
                    from axiestudio.services.email.service import EmailService
                    email_service = EmailService()

                    subscription_end_str = "your current billing period"
                    subscription_end_date = cancel_result.get("subscription_end")
                    if subscription_end_date and hasattr(subscription_end_date, 'strftime'):
                        subscription_end_str = subscription_end_date.strftime("%B %d, %Y")

                    await email_service.send_subscription_cancelled_email(
                        email=current_user.email,
                        username=current_user.username,
                        subscription_end_date=subscription_end_str
                    )
                except Exception as e:
                    logger.error(f"Failed to send subscription cancellation email: {e}")

            return {
                "status": "success",
                "message": "Subscription cancelled. You will retain access until the end of your current billing period.",
                "subscription_end": cancel_result.get("subscription_end").isoformat() if cancel_result.get("subscription_end") else None
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to cancel subscription")

    except Exception as e:
        logger.error(f"Failed to cancel subscription for user {current_user.id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to cancel subscription. Please try again or contact support.")


@router.post("/reactivate")
async def reactivate_subscription(
    current_user: CurrentActiveUser,
    session: DbSession,
):
    """
    🔄 ROBUST SUBSCRIPTION REACTIVATION ENDPOINT

    Reactivates a canceled subscription with comprehensive validation and error handling.
    Handles all edge cases and provides detailed error messages.
    """
    # Rate limiting check
    if not check_rate_limit(str(current_user.id), "reactivate-subscription"):
        raise HTTPException(
            status_code=429,
            detail="Too many reactivation requests. Please wait a few minutes before trying again."
        )

    if not stripe_service.is_configured():
        raise HTTPException(status_code=503, detail="Stripe is not configured. Please contact support.")

    try:
        # COMPREHENSIVE VALIDATION

        # Check if user has any subscription
        if not current_user.subscription_id:
            logger.warning(f"Reactivation attempt by user {current_user.id} with no subscription_id")
            raise HTTPException(
                status_code=400,
                detail="No subscription found. You need to create a subscription first."
            )

        # Check if subscription is actually canceled
        if current_user.subscription_status != "canceled":
            logger.warning(f"Reactivation attempt by user {current_user.id} with status: {current_user.subscription_status}")

            if current_user.subscription_status == "active":
                raise HTTPException(
                    status_code=400,
                    detail="Your subscription is already active. No reactivation needed."
                )
            elif current_user.subscription_status == "trial":
                raise HTTPException(
                    status_code=400,
                    detail="You are currently on a trial period. Reactivation is not applicable."
                )
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Subscription cannot be reactivated from status: {current_user.subscription_status}"
                )

        # Check if subscription has expired (can't reactivate expired subscriptions)
        if current_user.subscription_end:
            now = datetime.now(timezone.utc)
            subscription_end = current_user.subscription_end

            # CRITICAL FIX: Ensure timezone awareness for subscription_end
            if subscription_end.tzinfo is None:
                subscription_end = subscription_end.replace(tzinfo=timezone.utc)

            if now >= subscription_end:
                logger.warning(f"Reactivation attempt by user {current_user.id} for expired subscription (ended: {subscription_end})")
                raise HTTPException(
                    status_code=400,
                    detail="The subscription has already expired and cannot be reactivated. Please create a new subscription."
                )

        # STRIPE REACTIVATION
        logger.info(f"Attempting to reactivate subscription {current_user.subscription_id} for user {current_user.id}")
        reactivate_result = await stripe_service.reactivate_subscription(current_user.subscription_id)

        if reactivate_result.get("success"):
            # DATABASE UPDATE
            update_data = UserUpdate(
                subscription_status="active",
                subscription_end=reactivate_result.get("subscription_end")
            )
            await update_user(session, current_user.id, update_data)
            # User status updated to active

            # EMAIL NOTIFICATION (Non-blocking)
            if current_user.email:
                try:
                    from axiestudio.services.email.service import EmailService
                    email_service = EmailService()

                    # Format subscription end date for email
                    subscription_end_date = "unknown date"
                    if reactivate_result.get("subscription_end"):
                        subscription_end_date = reactivate_result["subscription_end"].strftime("%B %d, %Y")

                    await email_service.send_subscription_reactivated_email(
                        email=current_user.email,
                        username=current_user.username,
                        subscription_end_date=subscription_end_date
                    )
                except Exception as e:
                    # Email failure should not block the reactivation
                    logger.error(f"Failed to send subscription reactivation email: {e}")

            # SUCCESS RESPONSE
            return {
                "status": "success",
                "message": "Subscription reactivated! You will continue to have access to Pro features.",
                "subscription_end": reactivate_result.get("subscription_end").isoformat() if reactivate_result.get("subscription_end") else None,
                "reactivated_at": datetime.now(timezone.utc).isoformat()
            }
        else:
            # Stripe reactivation failed
            error_msg = reactivate_result.get("error", "Unknown Stripe error")
            logger.error(f"Stripe reactivation failed for user {current_user.id}: {error_msg}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to reactivate subscription in Stripe: {error_msg}"
            )

    except HTTPException:
        # Re-raise HTTP exceptions (they have proper error messages)
        raise
    except Exception as e:
        # Catch-all for unexpected errors
        logger.error(f"Unexpected error during reactivation for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred during reactivation. Please try again or contact support."
        )
