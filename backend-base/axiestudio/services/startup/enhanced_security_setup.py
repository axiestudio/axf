"""
Enhanced Security Setup Service
Auto-adds enhanced security columns to user table if they don't exist
Following the same pattern as subscription_setup.py
"""

import asyncio
from sqlalchemy import text
from axiestudio.logging import logger

from axiestudio.services.deps import get_db_service


async def setup_enhanced_security_columns():
    """
    Add enhanced security columns to user table if they don't exist.
    Follows the same pattern as subscription setup.
    """
    logger.info("🔐 Setting up enhanced security columns...")
    
    try:
        db_service = get_db_service()
        
        async with db_service.with_session() as session:
            # Check if we're using SQLite or PostgreSQL
            db_url = str(db_service.database_url).lower()
            is_sqlite = "sqlite" in db_url
            
            logger.debug(f"Database type: {'SQLite' if is_sqlite else 'PostgreSQL'}")
            
            # Get existing columns in user table
            if is_sqlite:
                result = await session.exec(text("PRAGMA table_info(user)"))
                existing_columns = [row[1] for row in result.fetchall()]  # Column name is at index 1
            else:
                result = await session.exec(text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'user' AND table_schema = 'public'
                """))
                existing_columns = [row[0] for row in result.fetchall()]
            
            logger.debug(f"Existing columns in user table: {existing_columns}")
            
            # Define enhanced security columns to add
            # Following the same pattern as subscription columns
            enhanced_security_columns = {
                "login_attempts": "INTEGER DEFAULT 0",
                "locked_until": "TIMESTAMP",
                "last_login_ip": "VARCHAR",
                "password_changed_at": "TIMESTAMP", 
                "failed_login_attempts": "INTEGER DEFAULT 0",
                "last_failed_login": "TIMESTAMP"
            }
            
            # For SQLite, we need different syntax
            if is_sqlite:
                enhanced_security_columns = {
                    "login_attempts": "INTEGER DEFAULT 0",
                    "locked_until": "DATETIME",
                    "last_login_ip": "TEXT",
                    "password_changed_at": "DATETIME",
                    "failed_login_attempts": "INTEGER DEFAULT 0",
                    "last_failed_login": "DATETIME"
                }
            else:
                # PostgreSQL syntax (already defined above)
                pass
            
            # Build migration commands for missing columns only
            migration_commands = []
            for column_name, column_def in enhanced_security_columns.items():
                if column_name not in existing_columns:
                    if is_sqlite:
                        migration_commands.append(f"ALTER TABLE user ADD COLUMN {column_name} {column_def};")
                    else:
                        migration_commands.append(f'ALTER TABLE "user" ADD COLUMN {column_name} {column_def};')
                else:
                    logger.debug(f"Column {column_name} already exists, skipping")
            
            if not migration_commands:
                logger.info("All enhanced security columns already exist, skipping schema migration")
                return True
            else:
                logger.info(f"Adding {len(migration_commands)} missing enhanced security columns: {list(enhanced_security_columns.keys())}")
            
            # Execute migration commands
            for command in migration_commands:
                try:
                    logger.debug(f"Executing: {command}")
                    await session.exec(text(command))
                    logger.debug("✅ Command executed successfully")
                except Exception as e:
                    logger.error(f"❌ Failed to execute command '{command}': {e}")
                    # Continue with other commands even if one fails
                    continue
            
            # Commit all changes
            await session.commit()
            logger.info("✅ Enhanced security schema migration completed successfully")
            
            # Create indexes for performance (if they don't exist)
            index_commands = []
            if is_sqlite:
                index_commands = [
                    "CREATE INDEX IF NOT EXISTS ix_user_login_attempts ON user (login_attempts);",
                    "CREATE INDEX IF NOT EXISTS ix_user_locked_until ON user (locked_until);",
                    "CREATE INDEX IF NOT EXISTS ix_user_last_login_ip ON user (last_login_ip);"
                ]
            else:
                index_commands = [
                    'CREATE INDEX IF NOT EXISTS ix_user_login_attempts ON "user" (login_attempts);',
                    'CREATE INDEX IF NOT EXISTS ix_user_locked_until ON "user" (locked_until);',
                    'CREATE INDEX IF NOT EXISTS ix_user_last_login_ip ON "user" (last_login_ip);'
                ]
            
            # Execute index creation commands
            for command in index_commands:
                try:
                    logger.debug(f"Creating index: {command}")
                    await session.exec(text(command))
                except Exception as e:
                    logger.warning(f"⚠️ Index creation warning: {e}")
                    # Indexes are not critical, continue
                    continue
            
            await session.commit()
            logger.info("✅ Enhanced security indexes created successfully")
            
            return True
            
    except Exception as e:
        logger.error(f"❌ Enhanced security setup failed: {e}")
        return False


async def verify_enhanced_security_setup():
    """Verify that enhanced security columns exist and are properly configured."""
    logger.info("🔍 Verifying enhanced security setup...")
    
    try:
        db_service = get_db_service()
        
        async with db_service.with_session() as session:
            # Check if we're using SQLite or PostgreSQL
            db_url = str(db_service.database_url).lower()
            is_sqlite = "sqlite" in db_url
            
            # Get existing columns
            if is_sqlite:
                result = await session.exec(text("PRAGMA table_info(user)"))
                existing_columns = [row[1] for row in result.fetchall()]
            else:
                result = await session.exec(text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'user' AND table_schema = 'public'
                """))
                existing_columns = [row[0] for row in result.fetchall()]
            
            # Check required columns
            required_columns = [
                "login_attempts",
                "locked_until", 
                "last_login_ip",
                "password_changed_at",
                "failed_login_attempts",
                "last_failed_login"
            ]
            
            missing_columns = []
            for column in required_columns:
                if column not in existing_columns:
                    missing_columns.append(column)
                else:
                    logger.debug(f"✅ Column {column} exists")
            
            if missing_columns:
                logger.warning(f"⚠️ Missing enhanced security columns: {missing_columns}")
                return False
            else:
                logger.info("✅ All enhanced security columns exist")
                return True
                
    except Exception as e:
        logger.error(f"❌ Enhanced security verification failed: {e}")
        return False


# Main setup function that can be called during startup
async def initialize_enhanced_security():
    """
    Initialize enhanced security features.
    This function should be called during app startup.
    """
    logger.info("🚀 Initializing enhanced security features...")
    
    # Step 1: Setup columns
    setup_success = await setup_enhanced_security_columns()
    if not setup_success:
        logger.error("❌ Enhanced security column setup failed")
        return False
    
    # Step 2: Verify setup
    verify_success = await verify_enhanced_security_setup()
    if not verify_success:
        logger.error("❌ Enhanced security verification failed")
        return False
    
    logger.info("🎉 Enhanced security initialization completed successfully")
    return True


if __name__ == "__main__":
    # For testing purposes
    asyncio.run(initialize_enhanced_security())
