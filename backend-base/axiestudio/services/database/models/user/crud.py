from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from axiestudio.logging import logger
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from axiestudio.services.database.models.user.model import User, UserUpdate
from typing import List


async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    stmt = select(User).where(User.username == username)
    user = (await db.exec(stmt)).first()

    # CRITICAL FIX: Force refresh user object to get latest subscription status
    # This prevents stale data issues when webhooks update subscription status
    if user:
        await db.refresh(user)

    return user


async def get_user_by_id(db: AsyncSession, user_id: UUID) -> User | None:
    if isinstance(user_id, str):
        user_id = UUID(user_id)
    stmt = select(User).where(User.id == user_id)
    user = (await db.exec(stmt)).first()

    # CRITICAL FIX: Force refresh user object to get latest subscription status
    # This prevents stale data issues when webhooks update subscription status
    if user:
        await db.refresh(user)

    return user


async def get_user_by_stripe_customer_id(db: AsyncSession, stripe_customer_id: str) -> User | None:
    stmt = select(User).where(User.stripe_customer_id == stripe_customer_id)
    user = (await db.exec(stmt)).first()

    # CRITICAL FIX: Force refresh user object to get latest subscription status
    # This prevents stale data issues when webhooks update subscription status
    if user:
        await db.refresh(user)

    return user


async def update_user(db: AsyncSession, user_id: UUID, user: UserUpdate) -> User:
    user_db = await get_user_by_id(db, user_id)
    return await update_user_instance(user_db, user, db)


async def update_user_instance(user_db: User | None, user: UserUpdate, db: AsyncSession) -> User:
    if not user_db:
        raise HTTPException(status_code=404, detail="User not found")

    # user_db_by_username = get_user_by_username(db, user.username)
    # if user_db_by_username and user_db_by_username.id != user_id:
    #     raise HTTPException(status_code=409, detail="Username already exists")

    user_data = user.model_dump(exclude_unset=True)
    changed = False
    for attr, value in user_data.items():
        if hasattr(user_db, attr) and value is not None:
            setattr(user_db, attr, value)
            changed = True

    if not changed:
        raise HTTPException(status_code=status.HTTP_304_NOT_MODIFIED, detail="Nothing to update")

    user_db.updated_at = datetime.now(timezone.utc)
    flag_modified(user_db, "updated_at")

    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e

    return user_db


async def update_user_last_login_at(user_id: UUID, db: AsyncSession):
    try:
        user_data = UserUpdate(last_login_at=datetime.now(timezone.utc))
        user = await get_user_by_id(db, user_id)
        return await update_user_instance(user, user_data, db)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error updating user last login at: {e!s}")


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    """Get user by email address."""
    stmt = select(User).where(User.email == email)
    user = (await db.exec(stmt)).first()

    # CRITICAL FIX: Force refresh user object to get latest subscription status
    # This prevents stale data issues when webhooks update subscription status
    if user:
        await db.refresh(user)

    return user


async def get_users_by_signup_ip(db: AsyncSession, signup_ip: str, limit: int = 10) -> List[User]:
    """Get users who signed up from the same IP address."""
    stmt = select(User).where(User.signup_ip == signup_ip).limit(limit)
    result = await db.exec(stmt)
    return result.all()


async def get_users_by_device_fingerprint(db: AsyncSession, device_fingerprint: str, limit: int = 10) -> List[User]:
    """Get users with the same device fingerprint."""
    stmt = select(User).where(User.device_fingerprint == device_fingerprint).limit(limit)
    result = await db.exec(stmt)
    return result.all()
