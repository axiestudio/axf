"""
Auto Migration Manager for AxieStudio
Handles automatic database schema updates and table creation
"""

import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Any
from axiestudio.logging import logger
from sqlalchemy import text, inspect
from sqlmodel import select

from axiestudio.services.deps import get_db_service
from axiestudio.services.database.models.user.model import User


class AutoMigrationManager:
    """Manages automatic database migrations and schema updates."""
    
    def __init__(self):
        self.db_service = None
    
    def _get_db_service(self):
        """Get database service instance."""
        if not self.db_service:
            self.db_service = get_db_service()
        return self.db_service
    
    async def get_database_info(self) -> Dict[str, Any]:
        """Get comprehensive database information."""
        try:
            db_service = self._get_db_service()
            
            async with db_service.with_session() as session:
                # Get database dialect
                dialect = session.bind.dialect.name
                
                # Get table count
                inspector = inspect(session.bind)
                table_names = inspector.get_table_names()
                table_count = len(table_names)
                
                # Get alembic version
                alembic_version = "Not initialized"
                try:
                    result = await session.exec(text("SELECT version_num FROM alembic_version"))
                    version = result.first()
                    if version:
                        alembic_version = version[0]
                except Exception:
                    pass
                
                return {
                    "dialect": dialect,
                    "table_count": table_count,
                    "table_names": table_names,
                    "alembic_version": alembic_version,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                
        except Exception as e:
            logger.error(f"Failed to get database info: {e}")
            return {"error": str(e)}
    
    async def check_migration_status(self) -> Dict[str, Any]:
        """Check the current migration status."""
        try:
            db_service = self._get_db_service()
            
            async with db_service.with_session() as session:
                # Check if user table exists and has required columns
                inspector = inspect(session.bind)
                
                if "user" not in inspector.get_table_names():
                    return {
                        "migration_status": "needs_initialization",
                        "message": "User table does not exist"
                    }
                
                # Check for email verification columns
                user_columns = [col['name'] for col in inspector.get_columns('user')]
                
                required_columns = [
                    'email_verified',
                    'email_verification_token', 
                    'email_verification_expires',
                    'verification_code',
                    'verification_code_expires',
                    'verification_attempts'
                ]
                
                missing_columns = [col for col in required_columns if col not in user_columns]
                
                if missing_columns:
                    return {
                        "migration_status": "needs_migration",
                        "missing_columns": missing_columns,
                        "message": f"Missing {len(missing_columns)} email verification columns"
                    }
                
                return {
                    "migration_status": "up_to_date",
                    "message": "All required columns present"
                }
                
        except Exception as e:
            logger.error(f"Failed to check migration status: {e}")
            return {
                "migration_status": "error",
                "error": str(e)
            }
    
    async def auto_create_missing_tables(self) -> Dict[str, Any]:
        """Automatically create missing tables."""
        try:
            db_service = self._get_db_service()
            
            # Use the existing create_db_and_tables method
            await db_service.create_db_and_tables()
            
            return {
                "success": True,
                "created_tables": ["user", "flow", "apikey", "folder", "message", "variable", "transaction", "vertex_build"],
                "errors": []
            }
            
        except Exception as e:
            logger.error(f"Failed to create missing tables: {e}")
            return {
                "success": False,
                "created_tables": [],
                "errors": [str(e)]
            }
    
    async def run_auto_migration(self, force: bool = False) -> Dict[str, Any]:
        """Run automatic migration process."""
        try:
            db_service = self._get_db_service()
            
            # Run migrations using the existing method
            await db_service.run_migrations(fix=force)
            
            return {
                "success": True,
                "message": "Migration completed successfully",
                "errors": []
            }
            
        except Exception as e:
            logger.error(f"Failed to run auto migration: {e}")
            return {
                "success": False,
                "message": f"Migration failed: {e}",
                "errors": [str(e)]
            }
    
    async def verify_email_verification_schema(self) -> Dict[str, Any]:
        """Verify that email verification schema is properly set up."""
        try:
            db_service = self._get_db_service()
            
            async with db_service.with_session() as session:
                inspector = inspect(session.bind)
                
                if "user" not in inspector.get_table_names():
                    return {
                        "status": "error",
                        "message": "User table does not exist"
                    }
                
                user_columns = [col['name'] for col in inspector.get_columns('user')]
                
                # Check for all email verification fields
                verification_fields = {
                    'email_verified': 'Legacy email verification status',
                    'email_verification_token': 'Legacy verification token',
                    'email_verification_expires': 'Legacy token expiry',
                    'verification_code': '6-digit verification code',
                    'verification_code_expires': '6-digit code expiry',
                    'verification_attempts': 'Failed verification attempts counter'
                }
                
                present_fields = []
                missing_fields = []
                
                for field, description in verification_fields.items():
                    if field in user_columns:
                        present_fields.append(f"{field} - {description}")
                    else:
                        missing_fields.append(f"{field} - {description}")
                
                # Test if we can query the user table
                try:
                    result = await session.exec(select(User).limit(1))
                    user_count = len(result.all())
                except Exception as e:
                    return {
                        "status": "error",
                        "message": f"Cannot query user table: {e}"
                    }
                
                return {
                    "status": "success" if not missing_fields else "incomplete",
                    "present_fields": present_fields,
                    "missing_fields": missing_fields,
                    "user_count": user_count,
                    "message": "Email verification schema verified" if not missing_fields else f"Missing {len(missing_fields)} fields"
                }
                
        except Exception as e:
            logger.error(f"Failed to verify email verification schema: {e}")
            return {
                "status": "error",
                "message": str(e)
            }


# Global instance
auto_migration_manager = AutoMigrationManager()
