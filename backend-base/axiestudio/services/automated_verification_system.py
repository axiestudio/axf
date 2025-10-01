#!/usr/bin/env python3
"""
Automated Email Verification System
This system will:
1. Automatically detect and fix broken email verifications
2. Run as a background task to monitor verification issues
3. Provide proper logging and error handling
4. Ensure users are properly activated after email verification
"""

import asyncio
from datetime import datetime, timezone, timedelta


# Import centralized timezone utility
from axiestudio.utils.timezone import ensure_timezone_aware

async def automated_verification_monitor():
    """Monitor and fix email verification issues automatically."""
    
    try:
        from axiestudio.services.deps import get_db_service
        from axiestudio.services.database.models.user.model import User
        from sqlmodel import select
        from axiestudio.logging import logger
        
        print("🤖 Starting Automated Email Verification Monitor")
        print("=" * 60)
        
        db_service = get_db_service()
        
        async with db_service.with_session() as session:
            
            # 1. Find users who should be verified but aren't
            print("🔍 Scanning for verification issues...")
            
            # Users with expired tokens but still unverified
            expired_token_stmt = select(User).where(
                User.email_verification_expires < datetime.now(timezone.utc),
                User.email_verified == False,
                User.email_verification_token.is_not(None)
            )
            expired_token_users = (await session.exec(expired_token_stmt)).all()
            
            # Users who are verified but not active
            verified_inactive_stmt = select(User).where(
                User.email_verified == True,
                User.is_active == False
            )
            verified_inactive_users = (await session.exec(verified_inactive_stmt)).all()
            
            # Users who are active but not verified (shouldn't happen)
            active_unverified_stmt = select(User).where(
                User.is_active == True,
                User.email_verified == False
            )
            active_unverified_users = (await session.exec(active_unverified_stmt)).all()
            
            total_issues = len(expired_token_users) + len(verified_inactive_users) + len(active_unverified_users)
            
            if total_issues == 0:
                print("✅ No verification issues found!")
                return True
            
            print(f"🚨 Found {total_issues} verification issues:")
            print(f"   - {len(expired_token_users)} users with expired tokens")
            print(f"   - {len(verified_inactive_users)} verified but inactive users")
            print(f"   - {len(active_unverified_users)} active but unverified users")
            
            # 2. Fix expired token users (auto-verify if token expired recently)
            fixed_count = 0
            
            for user in expired_token_users:
                # If token expired within last 7 days, auto-verify
                if user.email_verification_expires:
                    # Ensure timezone-aware comparison
                    user_expires = ensure_timezone_aware(user.email_verification_expires)
                    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)

                    if user_expires and user_expires > seven_days_ago:
                        print(f"🔧 Auto-verifying user with recently expired token: {user.username}")
                        user.email_verified = True
                        user.is_active = True
                        user.email_verification_token = None
                        user.email_verification_expires = None
                        user.updated_at = datetime.now(timezone.utc)
                        fixed_count += 1
                    else:
                        print(f"⚠️  User {user.username} has very old expired token - needs manual review")
                else:
                    print(f"⚠️  User {user.username} has no expiration date - needs manual review")
            
            # 3. Fix verified but inactive users
            for user in verified_inactive_users:
                print(f"🔧 Activating verified user: {user.username}")
                user.is_active = True
                user.updated_at = datetime.now(timezone.utc)
                fixed_count += 1
            
            # 4. Fix active but unverified users
            for user in active_unverified_users:
                print(f"🔧 Marking active user as verified: {user.username}")
                user.email_verified = True
                user.email_verification_token = None
                user.email_verification_expires = None
                user.updated_at = datetime.now(timezone.utc)
                fixed_count += 1
            
            # 5. Commit all fixes
            if fixed_count > 0:
                try:
                    await session.commit()
                    print(f"✅ Successfully fixed {fixed_count} verification issues!")
                    
                    # Log the fixes for audit trail
                    logger.info(f"Automated verification system fixed {fixed_count} user verification issues")
                    
                except Exception as e:
                    await session.rollback()
                    print(f"❌ Failed to commit fixes: {e}")
                    logger.error(f"Failed to commit automated verification fixes: {e}")
                    return False
            
            # 6. Generate summary report
            print("\n📊 VERIFICATION SYSTEM HEALTH REPORT")
            print("=" * 40)
            
            # Check overall system health
            total_users_stmt = select(User)
            total_users = len((await session.exec(total_users_stmt)).all())
            
            verified_active_stmt = select(User).where(
                User.email_verified == True,
                User.is_active == True
            )
            verified_active_users = len((await session.exec(verified_active_stmt)).all())
            
            pending_verification_stmt = select(User).where(
                User.email_verified == False,
                User.email_verification_token.is_not(None)
            )
            pending_users = len((await session.exec(pending_verification_stmt)).all())
            
            print(f"Total Users: {total_users}")
            print(f"Verified & Active: {verified_active_users}")
            print(f"Pending Verification: {pending_users}")
            if total_users > 0:
                print(f"System Health: {(verified_active_users/total_users*100):.1f}% verified")
            
            if pending_users > 0:
                print(f"\n⚠️  {pending_users} users still need to verify their email")
            
            return True
            
    except Exception as e:
        print(f"❌ Automated verification monitor failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def run_verification_health_check():
    """Run a quick health check of the verification system."""

    try:
        from axiestudio.services.deps import get_db_service
        from axiestudio.services.database.models.user.model import User
        from sqlmodel import select

        print("🏥 Email Verification System Health Check")
        print("=" * 50)

        db_service = get_db_service()

        async with db_service.with_session() as session:

            # Check for common issues
            issues = []

            # Issue 1: Users verified but not active
            stmt = select(User).where(User.email_verified == True, User.is_active == False)
            verified_inactive = (await session.exec(stmt)).all()
            if verified_inactive:
                issues.append(f"{len(verified_inactive)} verified users are not active")

            # Issue 2: Users active but not verified
            stmt = select(User).where(User.is_active == True, User.email_verified == False)
            active_unverified = (await session.exec(stmt)).all()
            if active_unverified:
                issues.append(f"{len(active_unverified)} active users are not verified")

            # Issue 3: Expired tokens
            stmt = select(User).where(
                User.email_verification_expires < datetime.now(timezone.utc),
                User.email_verified == False
            )
            expired_tokens = (await session.exec(stmt)).all()
            if expired_tokens:
                issues.append(f"{len(expired_tokens)} users have expired verification tokens")

            if issues:
                print("🚨 ISSUES FOUND:")
                for issue in issues:
                    print(f"   - {issue}")
                print("\n💡 Run automated_verification_monitor() to fix these issues")
                return False
            else:
                print("✅ Email verification system is healthy!")
                return True

    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return False


if __name__ == "__main__":
    print("🤖 Automated Email Verification System")
    print("Choose an option:")
    print("1. Run health check")
    print("2. Run automated monitor and fix")

    choice = input("Enter choice (1 or 2): ").strip()

    if choice == "1":
        success = asyncio.run(run_verification_health_check())
    elif choice == "2":
        success = asyncio.run(automated_verification_monitor())
    else:
        print("Invalid choice")
        success = False

    if success:
        print("\n🎉 System check completed successfully!")
    else:
        print("\n❌ System check found issues that need attention.")
