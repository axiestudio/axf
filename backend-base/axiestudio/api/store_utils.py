"""
Store utilities for Axie Studio.
Since store functionality is disabled, these are minimal implementations.
"""
import httpx
from axiestudio.logging import logger
from pydantic import BaseModel
from typing import Optional


class StoreComponentCreate(BaseModel):
    """Minimal store component schema for compatibility."""
    last_tested_version: Optional[str] = None


async def get_lf_version_from_pypi():
    """
    Get the latest released version of Axie Studio.
    Since store is disabled, this returns a placeholder version.
    """
    try:
        # For Axie Studio, we'll return the current version instead of checking PyPI
        # since we don't publish to PyPI and store functionality is disabled
        from axiestudio.utils.version import get_version_info
        return get_version_info()["version"]
    except Exception:  # noqa: BLE001
        logger.opt(exception=True).debug("Error getting Axie Studio version")
        return "1.0.0"  # Fallback version


def process_component_data(nodes_list):
    """Process component data for metadata."""
    names = [node["id"].split("-")[0] for node in nodes_list]
    metadata = {}
    for name in names:
        if name in metadata:
            metadata[name]["count"] += 1
        else:
            metadata[name] = {"count": 1}
    metadata["total"] = len(names)
    return metadata
