"""
ENTERPRISE-GRADE Webhook Event Model for Stripe Integration
Provides database-backed idempotency and audit trail for webhook processing.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel, Column, DateTime, Text
from sqlalchemy import text


class WebhookEventBase(SQLModel):
    """Base model for webhook events."""
    stripe_event_id: str = Field(unique=True, index=True, description="Stripe event ID for idempotency")
    event_type: str = Field(description="Type of Stripe event (e.g., checkout.session.completed)")
    status: str = Field(default="processing", description="Processing status: processing, completed, failed")
    error_message: Optional[str] = Field(default=None, sa_column=Column(Text), description="Error message if processing failed")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=Column(DateTime(timezone=True), nullable=False, server_default=text('NOW()')))
    completed_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class WebhookEvent(WebhookEventBase, table=True):
    """Database table for webhook events."""
    __tablename__ = "webhook_events"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)


class WebhookEventCreate(WebhookEventBase):
    """Model for creating webhook events."""
    pass


class WebhookEventRead(WebhookEventBase):
    """Model for reading webhook events."""
    id: UUID
