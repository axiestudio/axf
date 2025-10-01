"""Stripe service for handling subscriptions and payments."""

import os
from datetime import datetime, timezone, timedelta
from typing import Optional

try:
    import stripe
    STRIPE_AVAILABLE = True
except ImportError:
    STRIPE_AVAILABLE = False
    stripe = None

from axiestudio.logging import logger

from axiestudio.services.database.models.user.model import UserUpdate
from axiestudio.services.database.models.user.crud import update_user, get_user_by_stripe_customer_id


class StripeService:
    """Service for handling Stripe operations."""
    
    def __init__(self):
        """Initialize Stripe service with API key."""
        if not STRIPE_AVAILABLE:
            logger.warning("Stripe package not available - Stripe functionality will be disabled")
            self.stripe_secret_key = None
            self.stripe_price_id = None
            self.is_railway = False
            return

        self.stripe_secret_key = os.getenv("STRIPE_SECRET_KEY")
        self.stripe_price_id = os.getenv("STRIPE_PRICE_ID")
        self.is_railway = os.getenv("RAILWAY_ENVIRONMENT") == "production"

        if not self.stripe_secret_key:
            logger.warning("STRIPE_SECRET_KEY not found - Stripe functionality will be disabled")
            return

        if not self.stripe_price_id:
            logger.warning("STRIPE_PRICE_ID not found - using default price ID")
            self.stripe_price_id = "price_1RxD0RBacFXEnBmNI6T0IkOd"

        stripe.api_key = self.stripe_secret_key
        logger.info(f"Stripe service initialized for {'production' if self.is_railway else 'development'} environment")

    def is_configured(self) -> bool:
        """Check if Stripe is properly configured."""
        return bool(STRIPE_AVAILABLE and self.stripe_secret_key and self.stripe_price_id)
    
    async def create_customer(self, email: str, name: str) -> str:
        """Create a Stripe customer."""
        try:
            customer = stripe.Customer.create(
                email=email,
                name=name,
                metadata={"source": "axiestudio"}
            )
            logger.info(f"Created Stripe customer: {customer.id}")
            return customer.id
        except Exception as e:
            logger.error(f"Failed to create Stripe customer: {e}")
            raise
    
    async def create_checkout_session(
        self,
        customer_id: str,
        success_url: str,
        cancel_url: str,
        trial_days: int = 7
    ) -> str:
        """Create a Stripe checkout session with trial."""
        try:
            # FIXED: Handle trial_days = 0 case (Stripe doesn't accept 0-day trials)
            subscription_data = {
                'metadata': {
                    'source': 'axiestudio'
                }
            }

            # Only add trial if trial_days > 0 (Stripe requirement)
            if trial_days > 0:
                subscription_data['trial_period_days'] = trial_days
                logger.info(f"Creating checkout with {trial_days} trial days")
            else:
                logger.info("Creating checkout with no trial (immediate payment)")

            session = stripe.checkout.Session.create(
                customer=customer_id,
                payment_method_types=['card'],
                line_items=[{
                    'price': self.stripe_price_id,
                    'quantity': 1,
                }],
                mode='subscription',
                success_url=success_url,
                cancel_url=cancel_url,
                subscription_data=subscription_data,
                allow_promotion_codes=True,
            )
            logger.info(f"Created checkout session: {session.id}")
            return session.url
        except Exception as e:
            logger.error(f"Failed to create checkout session: {e}")
            raise
    
    async def create_customer_portal_session(self, customer_id: str, return_url: str) -> str:
        """Create a Stripe customer portal session."""
        try:
            session = stripe.billing_portal.Session.create(
                customer=customer_id,
                return_url=return_url,
            )
            logger.info(f"Created customer portal session: {session.id}")
            return session.url
        except Exception as e:
            logger.error(f"Failed to create customer portal session: {e}")
            raise
    
    async def get_subscription(self, subscription_id: str) -> Optional[dict]:
        """Get subscription details from Stripe with robust error handling."""
        try:
            subscription = stripe.Subscription.retrieve(subscription_id)

            # ROBUST HANDLING: Handle None/invalid timestamps
            current_period_start = None
            current_period_end = None
            trial_start = None
            trial_end = None

            # Safe timestamp conversion with validation
            if hasattr(subscription, 'current_period_start') and subscription.current_period_start:
                try:
                    current_period_start = datetime.fromtimestamp(subscription.current_period_start, tz=timezone.utc)
                except (ValueError, OSError, TypeError) as e:
                    logger.warning(f"Invalid current_period_start timestamp: {subscription.current_period_start}, error: {e}")

            if hasattr(subscription, 'current_period_end') and subscription.current_period_end:
                try:
                    current_period_end = datetime.fromtimestamp(subscription.current_period_end, tz=timezone.utc)
                except (ValueError, OSError, TypeError) as e:
                    logger.warning(f"Invalid current_period_end timestamp: {subscription.current_period_end}, error: {e}")

            if hasattr(subscription, 'trial_start') and subscription.trial_start:
                try:
                    trial_start = datetime.fromtimestamp(subscription.trial_start, tz=timezone.utc)
                except (ValueError, OSError, TypeError) as e:
                    logger.warning(f"Invalid trial_start timestamp: {subscription.trial_start}, error: {e}")

            if hasattr(subscription, 'trial_end') and subscription.trial_end:
                try:
                    trial_end = datetime.fromtimestamp(subscription.trial_end, tz=timezone.utc)
                except (ValueError, OSError, TypeError) as e:
                    logger.warning(f"Invalid trial_end timestamp: {subscription.trial_end}, error: {e}")

            return {
                'id': subscription.id,
                'status': subscription.status,
                'current_period_start': current_period_start,
                'current_period_end': current_period_end,
                'trial_start': trial_start,
                'trial_end': trial_end,
                'customer_id': subscription.customer
            }
        except stripe.error.InvalidRequestError as e:
            logger.error(f"Invalid Stripe subscription request for {subscription_id}: {e}")
            return None
        except stripe.error.StripeError as e:
            logger.error(f"Stripe API error getting subscription {subscription_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error getting subscription {subscription_id}: {e}")
            return None
    
    async def cancel_subscription(self, subscription_id: str) -> dict:
        """Cancel a subscription and return subscription details."""
        try:
            # Cancel the subscription (this sets it to cancel at period end)
            subscription = stripe.Subscription.modify(
                subscription_id,
                cancel_at_period_end=True
            )

            # Get the period end date
            period_end = datetime.fromtimestamp(subscription.current_period_end, tz=timezone.utc)

            logger.info(f"Cancelled subscription: {subscription_id}, will end at: {period_end}")
            return {
                "success": True,
                "subscription_end": period_end,
                "current_period_end": subscription.current_period_end
            }
        except Exception as e:
            logger.error(f"Failed to cancel subscription: {e}")
            return {"success": False}

    async def reactivate_subscription(self, subscription_id: str) -> dict:
        """
        🔄 ROBUST SUBSCRIPTION REACTIVATION

        Reactivates a canceled subscription with comprehensive error handling.
        Validates subscription state and handles all Stripe edge cases.
        """
        try:
            logger.info(f"🔄 Attempting to reactivate subscription: {subscription_id}")

            # STEP 1: Retrieve current subscription to validate state
            try:
                current_subscription = stripe.Subscription.retrieve(subscription_id)
            except stripe.error.InvalidRequestError as e:
                logger.error(f"❌ Invalid subscription ID {subscription_id}: {e}")
                return {
                    "success": False,
                    "error": f"Subscription not found: {subscription_id}"
                }

            # STEP 2: Validate subscription can be reactivated
            if current_subscription.status not in ["active", "past_due"]:
                logger.warning(f"⚠️  Cannot reactivate subscription {subscription_id} with status: {current_subscription.status}")
                return {
                    "success": False,
                    "error": f"Subscription cannot be reactivated from status: {current_subscription.status}"
                }

            # Check if subscription is actually canceled (has cancel_at_period_end=True)
            if not current_subscription.cancel_at_period_end:
                logger.warning(f"⚠️  Subscription {subscription_id} is not canceled (cancel_at_period_end=False)")
                return {
                    "success": False,
                    "error": "Subscription is not canceled and does not need reactivation"
                }

            # STEP 3: Reactivate by removing cancellation
            try:
                subscription = stripe.Subscription.modify(
                    subscription_id,
                    cancel_at_period_end=False
                )
                logger.info(f"✅ Successfully modified subscription {subscription_id}")
            except stripe.error.StripeError as e:
                logger.error(f"❌ Stripe error modifying subscription {subscription_id}: {e}")
                return {
                    "success": False,
                    "error": f"Stripe error during reactivation: {e.user_message or str(e)}"
                }

            # STEP 4: Calculate subscription end date
            try:
                period_end = datetime.fromtimestamp(subscription.current_period_end, tz=timezone.utc)
            except (ValueError, OSError) as e:
                logger.error(f"❌ Error parsing period end timestamp: {e}")
                # Fallback: use current time + 30 days
                period_end = datetime.now(timezone.utc) + timedelta(days=30)

            # STEP 5: Validate reactivation was successful
            if subscription.cancel_at_period_end:
                logger.error(f"❌ Reactivation failed - subscription {subscription_id} still has cancel_at_period_end=True")
                return {
                    "success": False,
                    "error": "Reactivation failed - subscription is still canceled"
                }

            logger.info(f"🎉 Successfully reactivated subscription: {subscription_id}, continues until: {period_end}")
            return {
                "success": True,
                "subscription_end": period_end,
                "current_period_end": subscription.current_period_end,
                "status": subscription.status,
                "cancel_at_period_end": subscription.cancel_at_period_end,
                "reactivated_at": datetime.now(timezone.utc)
            }

        except stripe.error.AuthenticationError as e:
            logger.error(f"❌ Stripe authentication error: {e}")
            return {
                "success": False,
                "error": "Stripe authentication error. Contact support."
            }
        except stripe.error.RateLimitError as e:
            logger.error(f"❌ Stripe rate limit error: {e}")
            return {
                "success": False,
                "error": "Too many requests to Stripe. Please try again in a moment."
            }
        except stripe.error.StripeError as e:
            logger.error(f"❌ General Stripe error during reactivation: {e}")
            return {
                "success": False,
                "error": f"Stripe error: {e.user_message or 'Unknown error'}"
            }
        except Exception as e:
            logger.error(f"❌ Unexpected error during subscription reactivation: {e}")
            return {
                "success": False,
                "error": f"Unexpected error during reactivation: {str(e)}"
            }
    
    async def handle_webhook_event(self, event_data: dict, session) -> bool:
        """Handle Stripe webhook events."""
        try:
            event_type = event_data.get('type')
            data = event_data.get('data', {}).get('object', {})

            logger.info(f"🔔 Processing Stripe webhook: {event_type}")

            if event_type == 'checkout.session.completed':
                await self._handle_checkout_completed(data, session)
            elif event_type == 'customer.subscription.created':
                await self._handle_subscription_created(data, session)
            elif event_type == 'customer.subscription.updated':
                await self._handle_subscription_updated(data, session)
            elif event_type == 'customer.subscription.deleted':
                await self._handle_subscription_deleted(data, session)
            elif event_type == 'invoice.payment_succeeded':
                await self._handle_payment_succeeded(data, session)
            elif event_type == 'invoice.payment_failed':
                await self._handle_payment_failed(data, session)
            elif event_type == 'invoice.finalized':
                await self._handle_invoice_finalized(data, session)
            elif event_type == 'invoice.paid':
                await self._handle_invoice_paid(data, session)
            else:
                logger.info(f"⚠️ Unhandled webhook event type: {event_type}")

            return True
        except Exception as e:
            logger.error(f"Failed to handle webhook event: {e}")
            return False

    async def _handle_checkout_completed(self, checkout_data: dict, session):
        """Handle checkout session completed event - ENTERPRISE TRIAL-TO-PAID UPGRADE."""
        try:
            customer_id = checkout_data.get('customer')
            subscription_id = checkout_data.get('subscription')

            logger.info(f"🚀 ENTERPRISE CHECKOUT: Trial-to-paid upgrade completed - Customer: {customer_id}, Subscription: {subscription_id}")

            if not customer_id:
                logger.error("No customer ID in checkout session")
                return

            # Find user by Stripe customer ID
            from axiestudio.services.database.models.user.crud import get_user_by_stripe_customer_id
            user = await get_user_by_stripe_customer_id(session, customer_id)
            if not user:
                logger.error(f"User not found for Stripe customer {customer_id}")
                return

            # If there's a subscription ID, get the subscription details
            if subscription_id:
                subscription_data = await self.get_subscription(subscription_id)
                if subscription_data:
                    # Extract subscription details
                    status = subscription_data.get('status', 'active')
                    current_period_start = subscription_data.get('current_period_start')
                    current_period_end = subscription_data.get('current_period_end')

                    # Convert timestamps to datetime objects - FIXED: Handle both datetime and timestamp
                    subscription_start = None
                    subscription_end = None

                    if current_period_start:
                        if isinstance(current_period_start, datetime):
                            subscription_start = current_period_start.replace(tzinfo=timezone.utc) if current_period_start.tzinfo is None else current_period_start
                        else:
                            subscription_start = datetime.fromtimestamp(current_period_start, tz=timezone.utc)

                    if current_period_end:
                        if isinstance(current_period_end, datetime):
                            subscription_end = current_period_end.replace(tzinfo=timezone.utc) if current_period_end.tzinfo is None else current_period_end
                        else:
                            subscription_end = datetime.fromtimestamp(current_period_end, tz=timezone.utc)

                    # ENTERPRISE PATTERN: Immediate trial-to-paid transition
                    update_data = UserUpdate(
                        subscription_status='active',  # ENTERPRISE: Immediate paid status
                        subscription_id=subscription_id,
                        subscription_start=subscription_start,
                        subscription_end=subscription_end
                    )

                    await update_user(session, user.id, update_data)
                    logger.info(f"🚀 ENTERPRISE UPGRADE: User {user.username} transitioned from trial to active subscription - NO additional trial days")
                    logger.info(f"🔍 DEBUG - User {user.username} updated with: status={update_data.subscription_status}, id={update_data.subscription_id}, start={update_data.subscription_start}, end={update_data.subscription_end}")

                    # CRITICAL: Commit the transaction immediately to ensure data is persisted
                    await session.commit()
                    logger.info(f"💾 Database transaction committed for user {user.username}")

                    # CRITICAL: Force refresh to ensure we have the latest data after commit
                    await session.refresh(user)

                    # CRITICAL: Additional database-level refresh to bypass any caching
                    from sqlalchemy import text
                    await session.execute(text("SELECT 1"))  # Force session sync
                    await session.refresh(user)

                    logger.info(f"🔄 User {user.username} DOUBLE-REFRESHED after commit - final status: {user.subscription_status}")

                    # CRITICAL: Flush all pending changes to ensure immediate visibility
                    await session.flush()
                    logger.info(f"🚀 Session flushed - user {user.username} subscription changes are now immediately visible")

                    # Send welcome email
                    if user.email:
                        try:
                            from axiestudio.services.email.service import EmailService
                            email_service = EmailService()

                            import asyncio
                            asyncio.create_task(
                                email_service.send_subscription_welcome_email(
                                    email=user.email,
                                    username=user.username,
                                    plan_name="Pro"
                                )
                            )
                            logger.info(f"📧 Queued welcome email for {user.username}")
                        except Exception as e:
                            logger.error(f"Failed to send welcome email: {e}")
                else:
                    logger.error(f"Could not retrieve subscription {subscription_id}")
            else:
                # No subscription ID - this might be a one-time payment or setup
                logger.warning("Checkout completed without subscription ID")

        except Exception as e:
            logger.error(f"Error handling checkout completed: {e}")

    async def _handle_subscription_created(self, subscription_data: dict, session):
        """Handle subscription created event."""
        customer_id = subscription_data.get('customer')
        subscription_id = subscription_data.get('id')
        status = subscription_data.get('status')

        # Find user by Stripe customer ID
        from axiestudio.services.database.models.user.crud import get_user_by_stripe_customer_id
        user = await get_user_by_stripe_customer_id(session, customer_id)

        if user:
            trial_end = None
            if subscription_data.get('trial_end'):
                trial_end_value = subscription_data['trial_end']
                if isinstance(trial_end_value, datetime):
                    trial_end = trial_end_value.replace(tzinfo=timezone.utc) if trial_end_value.tzinfo is None else trial_end_value
                else:
                    trial_end = datetime.fromtimestamp(trial_end_value, tz=timezone.utc)

            # Handle current_period_start - could be datetime or timestamp
            period_start_value = subscription_data['current_period_start']
            if isinstance(period_start_value, datetime):
                subscription_start = period_start_value.replace(tzinfo=timezone.utc) if period_start_value.tzinfo is None else period_start_value
            else:
                subscription_start = datetime.fromtimestamp(period_start_value, tz=timezone.utc)

            # Handle current_period_end - could be datetime or timestamp
            period_end_value = subscription_data['current_period_end']
            if isinstance(period_end_value, datetime):
                subscription_end = period_end_value.replace(tzinfo=timezone.utc) if period_end_value.tzinfo is None else period_end_value
            else:
                subscription_end = datetime.fromtimestamp(period_end_value, tz=timezone.utc)

            update_data = UserUpdate(
                subscription_id=subscription_id,
                subscription_status=status,
                trial_end=trial_end,
                subscription_start=subscription_start,
                subscription_end=subscription_end
            )
            await update_user(session, user.id, update_data)
            logger.info(f"✅ SUBSCRIPTION CREATED - Updated user {user.username} with subscription {subscription_id}, status: {status}")
            logger.info(f"🔍 DEBUG - User {user.username} subscription created with: status={status}, id={subscription_id}, start={subscription_start}, end={subscription_end}")

            # ENTERPRISE PATTERN: Explicit commit with proper logging
            await session.commit()
            logger.info(f"✅ User {user.username} subscription created - status: {status}")

            # 📧 Send welcome email for new subscriptions
            if user.email and status == 'active':
                try:
                    from axiestudio.services.email.service import EmailService
                    email_service = EmailService()

                    # Get plan name from subscription metadata or default to "Pro"
                    plan_name = subscription_data.get('metadata', {}).get('plan_name', 'Pro')

                    import asyncio
                    asyncio.create_task(
                        email_service.send_subscription_welcome_email(
                            email=user.email,
                            username=user.username,
                            plan_name=plan_name
                        )
                    )
                    logger.info(f"📧 Queued subscription welcome email for {user.username}")
                except Exception as e:
                    logger.error(f"Failed to send subscription welcome email: {e}")
    
    async def _handle_subscription_updated(self, subscription_data: dict, session):
        """Handle subscription updated event - CRITICAL: Handle reactivation scenarios properly."""
        customer_id = subscription_data.get('customer')
        subscription_id = subscription_data.get('id')
        status = subscription_data.get('status')
        cancel_at_period_end = subscription_data.get('cancel_at_period_end', False)

        from axiestudio.services.database.models.user.crud import get_user_by_stripe_customer_id
        user = await get_user_by_stripe_customer_id(session, customer_id)

        if user:
            # Handle current_period_start and current_period_end
            period_start_value = subscription_data['current_period_start']
            if isinstance(period_start_value, datetime):
                subscription_start = period_start_value.replace(tzinfo=timezone.utc) if period_start_value.tzinfo is None else period_start_value
            else:
                subscription_start = datetime.fromtimestamp(period_start_value, tz=timezone.utc)

            period_end_value = subscription_data['current_period_end']
            if isinstance(period_end_value, datetime):
                subscription_end = period_end_value.replace(tzinfo=timezone.utc) if period_end_value.tzinfo is None else period_end_value
            else:
                subscription_end = datetime.fromtimestamp(period_end_value, tz=timezone.utc)

            # CRITICAL FIX: Handle reactivation vs cancellation scenarios
            if cancel_at_period_end:
                # User canceled - subscription will end at period end
                new_status = 'canceled'
                # Keep the subscription_end as the actual end date
                logger.info(f"🚫 Subscription {subscription_id} canceled, will end at {subscription_end}")
            else:
                # Subscription is active (could be reactivation or normal update)
                if user.subscription_status == 'canceled' and status == 'active':
                    # This is a reactivation - subscription continues beyond current period
                    new_status = 'active'
                    logger.info(f"🔄 Subscription {subscription_id} reactivated for user {user.username}")
                else:
                    # Normal subscription update
                    new_status = status
                    logger.info(f"📝 Subscription {subscription_id} updated to status: {status}")

            update_data = UserUpdate(
                subscription_id=subscription_id,
                subscription_status=new_status,
                subscription_start=subscription_start,
                subscription_end=subscription_end
            )
            await update_user(session, user.id, update_data)
            logger.info(f"Updated user {user.id} subscription via webhook - Status: {new_status}, End: {subscription_end}")
    
    async def _handle_subscription_deleted(self, subscription_data: dict, session):
        """Handle subscription deleted event - this happens when subscription actually ends."""
        customer_id = subscription_data.get('customer')
        deleted_subscription_id = subscription_data.get('id')

        from axiestudio.services.database.models.user.crud import get_user_by_stripe_customer_id
        user = await get_user_by_stripe_customer_id(session, customer_id)

        if user:
            # CRITICAL FIX: Only clear subscription_id if it matches the deleted subscription
            # This prevents race conditions when user creates new subscription immediately
            should_clear_subscription_id = (
                user.subscription_id == deleted_subscription_id or
                user.subscription_id is None
            )

            # Get the subscription end date from the webhook data
            subscription_end = None
            if subscription_data.get('current_period_end'):
                subscription_end = datetime.fromtimestamp(subscription_data['current_period_end'], tz=timezone.utc)

            if should_clear_subscription_id:
                update_data = UserUpdate(
                    subscription_status='canceled',
                    subscription_id=None,  # Safe to clear since this subscription actually ended
                    subscription_end=subscription_end
                )
                logger.info(f"🗑️ Subscription {deleted_subscription_id} ended for user {user.username} - cleared subscription_id")
            else:
                # User has a different subscription now - don't clear subscription_id
                logger.info(f"🗑️ Old subscription {deleted_subscription_id} ended for user {user.username}, but user has new subscription {user.subscription_id}")
                # Don't update anything - user has moved to a new subscription
                return

            await update_user(session, user.id, update_data)
            logger.info(f"Subscription {deleted_subscription_id} ended for user {user.id} at {subscription_end}")
    
    async def _handle_payment_succeeded(self, invoice_data: dict, session):
        """Handle successful payment."""
        subscription_id = invoice_data.get('subscription')
        if subscription_id:
            subscription_data = await self.get_subscription(subscription_id)
            if subscription_data:
                await self._handle_subscription_updated(subscription_data, session)
    
    async def _handle_payment_failed(self, invoice_data: dict, session):
        """Handle failed payment."""
        customer_id = invoice_data.get('customer')

        from axiestudio.services.database.models.user.crud import get_user_by_stripe_customer_id
        user = await get_user_by_stripe_customer_id(session, customer_id)

        if user:
            update_data = UserUpdate(subscription_status='past_due')
            await update_user(session, user.id, update_data)
            logger.info(f"Marked user {user.id} as past due")

    async def _handle_invoice_finalized(self, invoice_data: dict, session):
        """Handle invoice finalized event."""
        try:
            customer_id = invoice_data.get('customer')
            subscription_id = invoice_data.get('subscription')
            invoice_id = invoice_data.get('id')

            logger.info(f"📄 Invoice finalized - Invoice: {invoice_id}, Customer: {customer_id}, Subscription: {subscription_id}")

            if not customer_id:
                logger.warning("No customer ID in invoice finalized event")
                return

            # Find user by Stripe customer ID
            user = await get_user_by_stripe_customer_id(session, customer_id)
            if not user:
                logger.warning(f"User not found for Stripe customer {customer_id} in invoice.finalized")
                return

            # If there's a subscription, ensure user subscription data is up to date
            if subscription_id:
                subscription_data = await self.get_subscription(subscription_id)
                if subscription_data:
                    # Update user subscription status if needed
                    current_status = subscription_data.get('status')
                    if current_status in ['active', 'trialing']:
                        update_data = UserUpdate(
                            subscription_status=current_status,
                            subscription_id=subscription_id
                        )
                        await update_user(session, user.id, update_data)
                        logger.info(f"✅ Updated user {user.username} subscription status to {current_status} via invoice.finalized")

        except Exception as e:
            logger.error(f"Error handling invoice finalized: {e}")

    async def _handle_invoice_paid(self, invoice_data: dict, session):
        """Handle invoice paid event."""
        try:
            customer_id = invoice_data.get('customer')
            subscription_id = invoice_data.get('subscription')
            invoice_id = invoice_data.get('id')
            amount_paid = invoice_data.get('amount_paid', 0) / 100  # Convert from cents to dollars

            logger.info(f"💰 Invoice paid - Invoice: {invoice_id}, Customer: {customer_id}, Subscription: {subscription_id}, Amount: ${amount_paid}")

            if not customer_id:
                logger.warning("No customer ID in invoice paid event")
                return

            # Find user by Stripe customer ID
            user = await get_user_by_stripe_customer_id(session, customer_id)
            if not user:
                logger.warning(f"User not found for Stripe customer {customer_id} in invoice.paid")
                return

            # If there's a subscription, ensure user is activated and subscription data is current
            if subscription_id:
                subscription_data = await self.get_subscription(subscription_id)
                if subscription_data:
                    status = subscription_data.get('status')
                    current_period_start = subscription_data.get('current_period_start')
                    current_period_end = subscription_data.get('current_period_end')

                    # Update user with latest subscription information
                    update_data = UserUpdate(
                        subscription_status='active',  # Invoice paid means subscription is active
                        subscription_id=subscription_id,
                        subscription_start=current_period_start,
                        subscription_end=current_period_end
                    )

                    await update_user(session, user.id, update_data)
                    logger.info(f"✅ Updated user {user.username} subscription to active via invoice.paid")

        except Exception as e:
            logger.error(f"Error handling invoice paid: {e}")




# Global instance
stripe_service = StripeService()
