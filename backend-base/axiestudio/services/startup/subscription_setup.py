"""Startup service to initialize subscription-related database schema."""

import asyncio
from axiestudio.logging import logger

try:
    from axiestudio.services.deps import get_db_service
    from sqlalchemy import text
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    logger.warning("Database services not available - skipping subscription setup")


async def setup_subscription_schema():
    """Set up subscription-related database schema on startup."""
    if not DB_AVAILABLE:
        logger.warning("Database not available - skipping subscription schema setup")
        return False

    try:
        # Get database service with error handling
        try:
            db_service = get_db_service()
            if not db_service:
                logger.warning("Database service not initialized - skipping subscription schema setup")
                return False
        except Exception as e:
            logger.warning(f"Failed to get database service: {e} - skipping subscription schema setup")
            return False
        
        # Check if we're using SQLite or PostgreSQL for appropriate syntax
        db_url = str(db_service.database_url).lower()
        is_sqlite = "sqlite" in db_url

        # Check which columns already exist to avoid errors
        existing_columns = set()
        try:
            if is_sqlite:
                # SQLite: Check table schema
                result = await session.exec(text("PRAGMA table_info(user);"))
                rows = result.fetchall()
                existing_columns = {row[1] for row in rows}  # Column name is at index 1
                logger.debug(f"SQLite existing columns: {existing_columns}")
            else:
                # PostgreSQL: Check information_schema
                result = await session.exec(text("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'user' AND table_schema = 'public';
                """))
                rows = result.fetchall()
                existing_columns = {row[0] for row in rows}
                logger.debug(f"PostgreSQL existing columns: {existing_columns}")
        except Exception as e:
            logger.warning(f"Could not check existing columns: {e}")
            existing_columns = set()

        # Define columns to add
        subscription_columns = {
            'email': 'VARCHAR(255) NULL',
            'stripe_customer_id': 'VARCHAR(255) NULL',
            'subscription_status': "VARCHAR(50) DEFAULT 'trial'",
            'subscription_id': 'VARCHAR(255) NULL',
            'trial_start': 'TIMESTAMP NULL',
            'trial_end': 'TIMESTAMP NULL',
            'subscription_start': 'TIMESTAMP NULL',
            'subscription_end': 'TIMESTAMP NULL'
        }

        # Build migration commands for missing columns only
        migration_commands = []
        for column_name, column_def in subscription_columns.items():
            if column_name not in existing_columns:
                if is_sqlite:
                    migration_commands.append(f"ALTER TABLE user ADD COLUMN {column_name} {column_def};")
                else:
                    migration_commands.append(f'ALTER TABLE "user" ADD COLUMN {column_name} {column_def};')
            else:
                logger.debug(f"Column {column_name} already exists, skipping")

        if not migration_commands:
            logger.info("All subscription columns already exist, skipping schema migration")
            return True
        else:
            logger.info(f"Adding {len(migration_commands)} missing subscription columns: {list(subscription_columns.keys())}")
        
        try:
            async with db_service.with_session() as session:
                logger.info("Setting up subscription database schema...")

                # First, try to add columns (these might fail if columns already exist)
                for i, command in enumerate(migration_commands, 1):
                    try:
                        # Use session.exec for raw SQL commands with text()
                        await session.exec(text(command))
                        logger.debug(f"Executed subscription schema command {i}/{len(migration_commands)}: {command.strip()}")
                    except Exception as e:
                        # Column might already exist, which is fine
                        logger.debug(f"Schema command {i} result: {e} - Command: {command.strip()}")

                # Commit the schema changes first
                try:
                    await session.commit()
                    logger.debug("Schema changes committed successfully")
                except Exception as e:
                    logger.warning(f"Failed to commit schema changes: {e}")
                    await session.rollback()
                    return False

                # Update existing users to have trial information if they don't have it
                try:
                    if is_sqlite:
                        # SQLite syntax
                        update_existing_users_query = text("""
                            UPDATE user
                            SET
                                trial_start = COALESCE(trial_start, create_at),
                                trial_end = COALESCE(trial_end, datetime(create_at, '+7 days')),
                                subscription_status = COALESCE(subscription_status, 'trial')
                            WHERE trial_start IS NULL OR subscription_status IS NULL;
                        """)
                    else:
                        # PostgreSQL syntax
                        update_existing_users_query = text("""
                            UPDATE "user"
                            SET
                                trial_start = COALESCE(trial_start, create_at),
                                trial_end = COALESCE(trial_end, create_at + INTERVAL '7 days'),
                                subscription_status = COALESCE(subscription_status, 'trial')
                            WHERE trial_start IS NULL OR subscription_status IS NULL;
                        """)

                    result = await session.exec(update_existing_users_query)
                    await session.commit()
                    logger.info("Successfully set up subscription database schema and updated existing users")
                    return True

                except Exception as e:
                    logger.warning(f"User update query failed: {e} - schema setup completed but user updates skipped")
                    await session.rollback()
                    # Schema setup was successful even if user updates failed
                    return True

        except Exception as e:
            logger.error(f"Database session error during subscription setup: {e}")
            return False
                
        return True
        
    except Exception as e:
        logger.error(f"Failed to set up subscription schema: {e}")
        return False


def run_subscription_setup():
    """Synchronous wrapper for subscription setup."""
    try:
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(setup_subscription_schema())
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Error running subscription setup: {e}")


# Don't auto-run on import - this will be called explicitly during app startup
# This prevents threading issues and startup hangs
logger.debug("Subscription setup module loaded - will run during app startup")
