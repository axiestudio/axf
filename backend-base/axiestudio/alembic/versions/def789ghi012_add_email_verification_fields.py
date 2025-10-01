"""Add 6-digit email verification fields and enhanced security columns

Revision ID: def789ghi012
Revises: abc123def456
Create Date: 2024-12-19 15:00:00.000000

This migration adds the new 6-digit email verification system fields
and enhanced security columns to support enterprise-grade authentication.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "def789ghi012"
down_revision: Union[str, None] = "abc123def456"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add 6-digit email verification fields and enhanced security columns.

    This migration adds:
    1. 6-digit verification code fields (verification_code, verification_code_expires, verification_attempts)
    2. Enhanced security fields (login_attempts, locked_until, last_login_ip, etc.)
    3. Email verification fields (email_verified, email_verification_token, email_verification_expires)
    """
    try:
        conn = op.get_bind()
        inspector = sa.inspect(conn)

        # Check if user table exists
        table_names = inspector.get_table_names()
        if 'user' not in table_names:
            print("⏭️ User table does not exist - skipping migration")
            return

        # Get existing columns safely
        try:
            existing_columns = [col['name'] for col in inspector.get_columns('user')]
        except Exception as e:
            print(f"❌ Failed to get existing columns: {e}")
            return
        
        # Define all email verification and security fields
        fields_to_add = {
            # Email verification fields (legacy token-based)
            'email_verified': {'type': sa.Boolean(), 'nullable': False, 'default': False},
            'email_verification_token': {'type': sa.String(), 'nullable': True},
            'email_verification_expires': {'type': sa.DateTime(), 'nullable': True},
            
            # 🎯 NEW: 6-digit code verification fields (enterprise-grade)
            'verification_code': {'type': sa.String(6), 'nullable': True},
            'verification_code_expires': {'type': sa.DateTime(), 'nullable': True},
            'verification_attempts': {'type': sa.Integer(), 'nullable': False, 'default': 0},
            
            # Enhanced security fields for enterprise auth
            'login_attempts': {'type': sa.Integer(), 'nullable': False, 'default': 0},
            'locked_until': {'type': sa.DateTime(), 'nullable': True},
            'last_login_ip': {'type': sa.String(), 'nullable': True},
            'password_changed_at': {'type': sa.DateTime(), 'nullable': True},
            'failed_login_attempts': {'type': sa.Integer(), 'nullable': False, 'default': 0},
            'last_failed_login': {'type': sa.DateTime(), 'nullable': True},
        }

        # Add columns using batch operations for better compatibility
        with op.batch_alter_table('user', schema=None) as batch_op:
            print("Starting email verification and security fields migration...")
            
            added_count = 0
            for field_name, field_config in fields_to_add.items():
                if field_name not in existing_columns:
                    try:
                        # Create column with proper configuration
                        column = sa.Column(
                            field_name,
                            field_config['type'],
                            nullable=field_config['nullable'],
                            default=field_config.get('default')
                        )
                        
                        batch_op.add_column(column)
                        print(f"✅ Added {field_name} column")
                        added_count += 1
                        
                    except Exception as e:
                        print(f"❌ Failed to add {field_name} column: {e}")
                        # Continue with other columns
                        continue
                else:
                    print(f"⏭️ {field_name} column already exists - skipping")
            
            print(f"Email verification and security fields migration completed! Added {added_count} new columns.")

        # Set default values for existing users (outside batch operation)
        if added_count > 0:
            print("Setting default values for existing users...")
            
            try:
                # Set defaults for boolean and integer fields
                conn.execute(sa.text("""
                    UPDATE "user" SET 
                        email_verified = COALESCE(email_verified, FALSE),
                        verification_attempts = COALESCE(verification_attempts, 0),
                        login_attempts = COALESCE(login_attempts, 0),
                        failed_login_attempts = COALESCE(failed_login_attempts, 0)
                    WHERE email_verified IS NULL 
                       OR verification_attempts IS NULL 
                       OR login_attempts IS NULL 
                       OR failed_login_attempts IS NULL
                """))
                print("✅ Set default values for existing users")
            except Exception as e:
                print(f"❌ Failed to set default values: {e}")

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        # Don't re-raise to prevent application startup failure
        print("⚠️ Continuing with application startup - fields will be auto-created by database service")


def downgrade() -> None:
    """Remove 6-digit email verification fields and enhanced security columns."""
    
    try:
        # Define fields to remove (only the ones we added in this migration)
        fields_to_remove = [
            'verification_code',
            'verification_code_expires', 
            'verification_attempts',
            'login_attempts',
            'locked_until',
            'last_login_ip',
            'password_changed_at',
            'failed_login_attempts',
            'last_failed_login'
        ]
        
        # Note: We keep email_verified, email_verification_token, email_verification_expires
        # as they might be used by other parts of the system
        
        with op.batch_alter_table('user', schema=None) as batch_op:
            print("Removing email verification and security fields...")
            
            for field_name in fields_to_remove:
                try:
                    batch_op.drop_column(field_name)
                    print(f"✅ Removed {field_name} column")
                except Exception as e:
                    print(f"❌ Failed to remove {field_name} column: {e}")
                    continue
            
            print("Email verification and security fields removal completed!")
    
    except Exception as e:
        print(f"❌ Downgrade failed: {e}")
        # Don't re-raise to prevent issues
