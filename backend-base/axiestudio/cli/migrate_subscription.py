"""CLI command to manually migrate subscription database schema."""

import asyncio
from axiestudio.logging import logger
from sqlalchemy import text

from axiestudio.services.deps import get_db_service


async def migrate_subscription_schema():
    """Add subscription columns to user table."""
    logger.info("🚀 Starting subscription schema migration...")
    
    try:
        db_service = get_db_service()
        db_url = str(db_service.database_url).lower()
        is_sqlite = "sqlite" in db_url
        
        logger.info(f"Database: {'SQLite' if is_sqlite else 'PostgreSQL'}")
        
        async with db_service.with_session() as session:
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
            
            # Define columns to add
            columns_to_add = [
                ('email', 'VARCHAR(255)'),
                ('stripe_customer_id', 'VARCHAR(255)'),
                ('subscription_status', "VARCHAR(50) DEFAULT 'trial'"),
                ('subscription_id', 'VARCHAR(255)'),
                ('trial_start', 'TIMESTAMP'),
                ('trial_end', 'TIMESTAMP'),
                ('subscription_start', 'TIMESTAMP'),
                ('subscription_end', 'TIMESTAMP')
            ]
            
            added = 0
            for column_name, column_def in columns_to_add:
                if column_name not in existing_columns:
                    try:
                        if is_sqlite:
                            sql = f"ALTER TABLE user ADD COLUMN {column_name} {column_def};"
                        else:
                            sql = f'ALTER TABLE "user" ADD COLUMN {column_name} {column_def};'
                        
                        await session.exec(text(sql))
                        logger.info(f"✅ Added: {column_name}")
                        added += 1
                    except Exception as e:
                        logger.error(f"❌ Failed to add {column_name}: {e}")
                else:
                    logger.info(f"⏭️  Exists: {column_name}")
            
            if added > 0:
                await session.commit()
                logger.info(f"🎉 Added {added} subscription columns!")
                
                # Set defaults for existing users
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
                    logger.info("✅ Updated existing users with defaults")
                except Exception as e:
                    logger.warning(f"⚠️  Failed to update users: {e}")
            else:
                logger.info("✅ All columns already exist!")
            
            return True
            
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        return False


def main():
    """Run the migration."""
    success = asyncio.run(migrate_subscription_schema())
    return 0 if success else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
