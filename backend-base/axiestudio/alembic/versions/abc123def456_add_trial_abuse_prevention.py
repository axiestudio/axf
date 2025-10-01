"""Add trial abuse prevention fields and fix email verification schema

Revision ID: abc123def456
Revises: 3162e83e485f
Create Date: 2024-12-19 12:00:00.000000

Note: This migration also fixes email verification schema issues
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "abc123def456"
down_revision: Union[str, None] = "3162e83e485f"  # Latest revision
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add trial abuse prevention fields and fix email verification schema.

    This migration:
    1. Adds signup_ip and device_fingerprint columns
    2. Fixes email_verified column to be NOT NULL
    3. Removes the ix_user_email_verification_token index if it exists
    """
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # Get existing columns and indexes
    existing_columns = [col['name'] for col in inspector.get_columns('user')]
    existing_indexes = [idx['name'] for idx in inspector.get_indexes('user')]

    # Add new columns if they don't exist
    with op.batch_alter_table('user', schema=None) as batch_op:
        print("Starting user table migration...")

        # Fix email_verified column to be NOT NULL (if it exists and is nullable)
        if 'email_verified' in existing_columns:
            try:
                # First, ensure all NULL values are set to FALSE
                conn.execute(sa.text("UPDATE \"user\" SET email_verified = FALSE WHERE email_verified IS NULL"))
                # Then alter the column to be NOT NULL
                batch_op.alter_column('email_verified', nullable=False, server_default=sa.text('FALSE'))
                print("Fixed email_verified column to be NOT NULL")
            except Exception as e:
                print(f"Failed to fix email_verified column: {e}")

        # Remove ix_user_email_verification_token index if it exists
        if 'ix_user_email_verification_token' in existing_indexes:
            try:
                batch_op.drop_index('ix_user_email_verification_token')
                print("Removed ix_user_email_verification_token index")
            except Exception as e:
                print(f"Failed to remove ix_user_email_verification_token index: {e}")

        # Add signup_ip column
        if 'signup_ip' not in existing_columns:
            try:
                batch_op.add_column(sa.Column('signup_ip', sa.String(45), nullable=True))
                print("Added signup_ip column")
            except Exception as e:
                print(f"Failed to add signup_ip column (may already exist): {e}")
        else:
            print("signup_ip column already exists - skipping creation")

        # Create signup_ip index only if it doesn't exist
        if 'ix_user_signup_ip' not in existing_indexes:
            try:
                batch_op.create_index('ix_user_signup_ip', ['signup_ip'])
                print("Created signup_ip index")
            except Exception as e:
                print(f"Failed to create signup_ip index (may already exist): {e}")
        else:
            print("signup_ip index already exists - skipping")

        # Add device_fingerprint column
        if 'device_fingerprint' not in existing_columns:
            try:
                batch_op.add_column(sa.Column('device_fingerprint', sa.String(32), nullable=True))
                print("Added device_fingerprint column")
            except Exception as e:
                print(f"Failed to add device_fingerprint column (may already exist): {e}")
        else:
            print("device_fingerprint column already exists - skipping creation")

        # Create device_fingerprint index only if it doesn't exist
        if 'ix_user_device_fingerprint' not in existing_indexes:
            try:
                batch_op.create_index('ix_user_device_fingerprint', ['device_fingerprint'])
                print("Created device_fingerprint index")
            except Exception as e:
                print(f"Failed to create device_fingerprint index (may already exist): {e}")
        else:
            print("device_fingerprint index already exists - skipping")

        print("User table migration completed successfully")


def downgrade() -> None:
    """Remove trial abuse prevention fields and revert email verification schema changes."""
    with op.batch_alter_table('user', schema=None) as batch_op:
        # Remove indexes first (only the ones we created)
        indexes_to_remove = ['ix_user_signup_ip', 'ix_user_device_fingerprint']
        for index_name in indexes_to_remove:
            try:
                batch_op.drop_index(index_name)
            except Exception:
                pass

        # Remove only the columns we added (not email or subscription fields)
        columns_to_remove = ['signup_ip', 'device_fingerprint']

        for column_name in columns_to_remove:
            try:
                batch_op.drop_column(column_name)
            except Exception:
                pass

        # Revert email_verified column to be nullable (if needed)
        try:
            batch_op.alter_column('email_verified', nullable=True)
            print("Reverted email_verified column to be nullable")
        except Exception:
            pass

        # Recreate ix_user_email_verification_token index if needed
        try:
            batch_op.create_index('ix_user_email_verification_token', ['email_verification_token'])
            print("Recreated ix_user_email_verification_token index")
        except Exception:
            pass

        # Note: We don't remove email or subscription fields as they're managed by other migrations
