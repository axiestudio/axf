from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from pydantic import BaseModel
from sqlalchemy import JSON, Column
from sqlmodel import Field, Relationship, SQLModel

from axiestudio.schema.serialize import UUIDstr

if TYPE_CHECKING:
    from axiestudio.services.database.models.api_key.model import ApiKey
    from axiestudio.services.database.models.flow.model import Flow
    from axiestudio.services.database.models.folder.model import Folder
    from axiestudio.services.database.models.variable.model import Variable


class UserOptin(BaseModel):
    github_starred: bool = Field(default=False)
    dialog_dismissed: bool = Field(default=False)
    discord_clicked: bool = Field(default=False)
    # Add more opt-in actions as needed


class User(SQLModel, table=True):  # type: ignore[call-arg]
    id: UUIDstr = Field(default_factory=uuid4, primary_key=True, unique=True)
    username: str = Field(index=True, unique=True)
    email: str | None = Field(default=None, nullable=True, index=True)  # Required for new users, nullable for existing users
    password: str = Field()
    profile_image: str | None = Field(default=None, nullable=True)
    is_active: bool = Field(default=False)
    is_superuser: bool = Field(default=False)
    create_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_login_at: datetime | None = Field(default=None, nullable=True)

    # Trial abuse prevention fields
    signup_ip: str | None = Field(default=None, nullable=True, index=True)  # Track signup IP
    device_fingerprint: str | None = Field(default=None, nullable=True, index=True)  # Track device fingerprint

    # Email verification fields (legacy token-based)
    email_verified: bool = Field(default=False)
    email_verification_token: str | None = Field(default=None, nullable=True)
    email_verification_expires: datetime | None = Field(default=None, nullable=True)

    # 🎯 NEW: 6-digit code verification fields (enterprise-grade)
    verification_code: str | None = Field(default=None, nullable=True, max_length=6)
    verification_code_expires: datetime | None = Field(default=None, nullable=True)
    verification_attempts: int = Field(default=0)  # Track failed attempts for security

    # Enhanced security fields for enterprise auth
    login_attempts: int = Field(default=0)
    locked_until: datetime | None = Field(default=None, nullable=True)
    last_login_ip: str | None = Field(default=None, nullable=True)
    password_changed_at: datetime | None = Field(default=None, nullable=True)
    failed_login_attempts: int = Field(default=0)
    last_failed_login: datetime | None = Field(default=None, nullable=True)

    # Subscription fields
    stripe_customer_id: str | None = Field(default=None, nullable=True)
    subscription_status: str | None = Field(default="trial", nullable=True)  # trial, active, canceled, past_due
    subscription_id: str | None = Field(default=None, nullable=True)
    trial_start: datetime | None = Field(default_factory=lambda: datetime.now(timezone.utc), nullable=True)
    trial_end: datetime | None = Field(default=None, nullable=True)
    subscription_start: datetime | None = Field(default=None, nullable=True)
    subscription_end: datetime | None = Field(default=None, nullable=True)
    api_keys: list["ApiKey"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "delete"},
    )
    store_api_key: str | None = Field(default=None, nullable=True)
    flows: list["Flow"] = Relationship(back_populates="user")
    variables: list["Variable"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "delete"},
    )
    folders: list["Folder"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "delete"},
    )
    optins: dict[str, Any] | None = Field(
        sa_column=Column(JSON, default=lambda: UserOptin().model_dump(), nullable=True)
    )


class UserCreate(SQLModel):
    username: str = Field()
    email: str = Field()  # Required for trial abuse prevention
    password: str = Field()
    optins: dict[str, Any] | None = Field(
        default={"github_starred": False, "dialog_dismissed": False, "discord_clicked": False}
    )
    trial_start: datetime | None = Field(default_factory=lambda: datetime.now(timezone.utc), nullable=True)

    # Trial abuse prevention fields (set by backend, not user input)
    signup_ip: str | None = Field(default=None, exclude=True)  # Exclude from user input
    device_fingerprint: str | None = Field(default=None, exclude=True)  # Exclude from user input


class UserRead(SQLModel):
    id: UUID = Field(default_factory=uuid4)
    username: str = Field()
    email: str | None = Field(default=None, nullable=True)  # Nullable for existing users
    profile_image: str | None = Field()
    store_api_key: str | None = Field(nullable=True)
    is_active: bool = Field()
    is_superuser: bool = Field()
    create_at: datetime = Field()
    updated_at: datetime = Field()
    last_login_at: datetime | None = Field(nullable=True)
    optins: dict[str, Any] | None = Field(default=None)

    # Email verification fields for read operations
    email_verified: bool = Field(default=False)

    # Subscription fields for read operations
    stripe_customer_id: str | None = Field(default=None, nullable=True)
    subscription_status: str | None = Field(default="trial", nullable=True)
    subscription_id: str | None = Field(default=None, nullable=True)
    trial_start: datetime | None = Field(default=None, nullable=True)
    trial_end: datetime | None = Field(default=None, nullable=True)
    subscription_start: datetime | None = Field(default=None, nullable=True)
    subscription_end: datetime | None = Field(default=None, nullable=True)


class UserUpdate(SQLModel):
    username: str | None = None
    email: str | None = None
    profile_image: str | None = None
    password: str | None = None
    is_active: bool | None = None
    is_superuser: bool | None = None
    last_login_at: datetime | None = None
    optins: dict[str, Any] | None = None

    # Subscription update fields
    stripe_customer_id: str | None = None
    subscription_status: str | None = None
    subscription_id: str | None = None
    trial_start: datetime | None = None
    trial_end: datetime | None = None
    subscription_start: datetime | None = None
    subscription_end: datetime | None = None

    # Trial abuse prevention fields (admin only)
    signup_ip: str | None = None
    device_fingerprint: str | None = None

    # Email verification update fields
    email_verified: bool | None = None
    email_verification_token: str | None = None
    email_verification_expires: datetime | None = None
