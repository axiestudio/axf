"""
Email Verification Scheduler
This runs the automated verification system on a schedule to ensure
all users are properly verified and activated.
"""

import asyncio
from datetime import datetime, timezone
from axiestudio.logging import logger


class VerificationScheduler:
    """Scheduler for automated email verification monitoring."""
    
    def __init__(self, interval_minutes: int = 30):
        self.interval_minutes = interval_minutes
        self.running = False
        self.task = None
    
    async def start(self):
        """Start the verification scheduler."""
        if self.running:
            logger.warning("Verification scheduler is already running")
            return
        
        self.running = True
        self.task = asyncio.create_task(self._run_scheduler())
        logger.info(f"Started verification scheduler (interval: {self.interval_minutes} minutes)")
    
    async def stop(self):
        """Stop the verification scheduler."""
        if not self.running:
            return
        
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        
        logger.info("Stopped verification scheduler")
    
    async def _run_scheduler(self):
        """Main scheduler loop."""
        while self.running:
            try:
                await self._run_verification_check()
                await asyncio.sleep(self.interval_minutes * 60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in verification scheduler: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retrying
    
    async def _run_verification_check(self):
        """Run the verification check and fix issues."""
        try:
            from .automated_verification_system import automated_verification_monitor

            logger.info("Running scheduled verification check...")
            success = await automated_verification_monitor()

            if success:
                logger.info("Scheduled verification check completed successfully")
            else:
                logger.warning("Scheduled verification check found issues")

        except Exception as e:
            logger.error(f"Failed to run scheduled verification check: {e}")


# Global scheduler instance
verification_scheduler = VerificationScheduler()


async def start_verification_scheduler():
    """Start the global verification scheduler."""
    await verification_scheduler.start()


async def stop_verification_scheduler():
    """Stop the global verification scheduler."""
    await verification_scheduler.stop()


# Add this to your FastAPI lifespan to enable automatic scheduling
async def verification_lifespan_handler(app):
    """Lifespan handler for verification scheduler."""
    
    # Startup
    logger.info("Starting email verification scheduler...")
    await start_verification_scheduler()
    
    yield
    
    # Shutdown
    logger.info("Stopping email verification scheduler...")
    await stop_verification_scheduler()
