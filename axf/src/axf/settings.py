"""Settings constants for axf package."""

import os

# Development mode flag - can be overridden by environment variable
DEV = os.getenv("AXIESTUDIO_DEV", "false").lower() == "true"
