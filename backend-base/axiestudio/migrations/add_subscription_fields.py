"""Migration script to add subscription fields to user table."""

import asyncio
from datetime import datetime, timezone, timedelta

from sqlalchemy import text
from axiestudio.logging import logger

from axiestudio.services.deps import get_db_service


async def add_subscription_fields():
    """Add subscription-related fields to the user table."""
    
    db_service = get_db_service()
    
    # SQL commands to add new columns
    migration_commands = [
        """
        ALTER TABLE user 
        ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR(255) NULL;
        """,
        """
        ALTER TABLE user 
        ADD COLUMN IF NOT EXISTS subscription_status VARCHAR(50) DEFAULT 'trial';
        """,
        """
        ALTER TABLE user 
        ADD COLUMN IF NOT EXISTS subscription_id VARCHAR(255) NULL;
        """,
        """
        ALTER TABLE user 
        ADD COLUMN IF NOT EXISTS trial_start TIMESTAMP NULL;
        """,
        """
        ALTER TABLE user 
        ADD COLUMN IF NOT EXISTS trial_end TIMESTAMP NULL;
        """,
        """
        ALTER TABLE user 
        ADD COLUMN IF NOT EXISTS subscription_start TIMESTAMP NULL;
        """,
        """
        ALTER TABLE user 
        ADD COLUMN IF NOT EXISTS subscription_end TIMESTAMP NULL;
        """
    ]
    
    try:
        async with db_service.with_session() as session:
            logger.info("Starting subscription fields migration...")
            
            for i, command in enumerate(migration_commands, 1):
                try:
                    await session.exec(text(command))
                    logger.info(f"Executed migration command {i}/{len(migration_commands)}")
                except Exception as e:
                    logger.warning(f"Command {i} may have already been applied: {e}")
            
            # Update existing users to have trial information
            update_existing_users_query = text("""
                UPDATE user 
                SET 
                    trial_start = COALESCE(trial_start, create_at),
                    trial_end = COALESCE(trial_end, datetime(create_at, '+7 days')),
                    subscription_status = COALESCE(subscription_status, 'trial')
                WHERE trial_start IS NULL OR subscription_status IS NULL;
            """)
            
            await session.exec(update_existing_users_query)
            await session.commit()
            
            logger.info("Successfully completed subscription fields migration")
            
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise


async def rollback_subscription_fields():
    """Rollback subscription fields migration (for development only)."""
    
    db_service = get_db_service()
    
    rollback_commands = [
        "ALTER TABLE user DROP COLUMN IF EXISTS stripe_customer_id;",
        "ALTER TABLE user DROP COLUMN IF EXISTS subscription_status;", 
        "ALTER TABLE user DROP COLUMN IF EXISTS subscription_id;",
        "ALTER TABLE user DROP COLUMN IF EXISTS trial_start;",
        "ALTER TABLE user DROP COLUMN IF EXISTS trial_end;",
        "ALTER TABLE user DROP COLUMN IF EXISTS subscription_start;",
        "ALTER TABLE user DROP COLUMN IF EXISTS subscription_end;"
    ]
    
    try:
        async with db_service.with_session() as session:
            logger.info("Starting subscription fields rollback...")
            
            for i, command in enumerate(rollback_commands, 1):
                try:
                    await session.exec(text(command))
                    logger.info(f"Executed rollback command {i}/{len(rollback_commands)}")
                except Exception as e:
                    logger.warning(f"Rollback command {i} failed: {e}")
            
            await session.commit()
            logger.info("Successfully completed subscription fields rollback")
            
    except Exception as e:
        logger.error(f"Rollback failed: {e}")
        raise


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        asyncio.run(rollback_subscription_fields())
    else:
        asyncio.run(add_subscription_fields())
