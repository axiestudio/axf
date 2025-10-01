import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/store", tags=["AxieStudio Store"])


class StoreAuthor(BaseModel):
    username: str
    full_name: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    id: Optional[str] = None


class StoreStats(BaseModel):
    downloads: int
    likes: int


class StoreDates(BaseModel):
    created: str
    updated: str
    downloaded: str


class StoreTag(BaseModel):
    tags_id: Dict[str, str]


class StoreConversion(BaseModel):
    converted_at: str
    converted_from: str
    converted_to: str
    conversions_made: int
    converter_version: str


class StoreItem(BaseModel):
    id: str
    name: str
    description: str
    type: str
    is_component: bool
    author: StoreAuthor
    store_url: str
    stats: StoreStats
    dates: StoreDates
    tags: List[StoreTag]
    technical: Optional[Dict[str, Any]] = None
    conversion: Optional[StoreConversion] = None


class StoreSummary(BaseModel):
    total_items: int
    total_flows: int
    total_components: int
    downloaded_at: str
    store_url: str
    api_used: str


class StoreConversionInfo(BaseModel):
    converted_at: str
    converted_from: str
    converted_to: str
    original_source: str
    converter_version: str


class StoreData(BaseModel):
    summary: StoreSummary
    flows: List[StoreItem]
    components: List[StoreItem]
    conversion_info: StoreConversionInfo


def get_store_components_path() -> Path:
    """Get the path to the converted store components directory."""
    # Get the path relative to the current file
    current_file = Path(__file__)
    # From temp/src/backend/base/axiestudio/api/v1/axiestudio_store.py
    # Go up to temp/src/ and then to store_components_converted
    # Path structure: axiestudio_store.py -> v1 -> api -> axiestudio -> base -> backend -> src
    # parents[0]=v1, parents[1]=api, parents[2]=axiestudio, parents[3]=base, parents[4]=backend, parents[5]=src
    # So parents[5] gets us to src/, then we add store_components_converted
    store_path = current_file.parents[5] / "store_components_converted"

    if not store_path.exists():
        # Try alternative paths for different deployment scenarios
        alternative_paths = [
            current_file.parents[5] / "src" / "store_components_converted",  # Docker deployment
            current_file.parents[3] / "store_components_converted",  # Local development
            Path("/app/src/store_components_converted"),  # Absolute Docker path
            Path("./src/store_components_converted"),  # Relative path
        ]

        for alt_path in alternative_paths:
            if alt_path.exists():
                store_path = alt_path
                break
        else:
            raise HTTPException(
                status_code=404,
                detail=f"AxieStudio Store components directory not found. Searched paths: {store_path}, {', '.join(str(p) for p in alternative_paths)}"
            )

    return store_path


def load_store_index() -> StoreData:
    """Load the main store index file."""
    try:
        store_path = get_store_components_path()
        index_file = store_path / "store_index.json"

        if not index_file.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Store index file not found at: {index_file}"
            )

        with open(index_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Validate that required fields exist
        if 'flows' not in data:
            data['flows'] = []
        if 'components' not in data:
            data['components'] = []
        if 'summary' not in data:
            data['summary'] = {
                'total_items': len(data.get('flows', [])) + len(data.get('components', [])),
                'total_flows': len(data.get('flows', [])),
                'total_components': len(data.get('components', [])),
                'downloaded_at': '2025-08-22T00:00:00.000Z',
                'store_url': 'https://www.langflow.store',
                'api_used': 'AxieStudio Store API'
            }
        if 'conversion_info' not in data:
            data['conversion_info'] = {
                'converted_at': '2025-08-22T00:00:00.000Z',
                'converted_from': 'langflow',
                'converted_to': 'axiestudio',
                'original_source': 'https://www.langflow.store',
                'converter_version': '1.0.0'
            }

        return StoreData(**data)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load store index: {str(e)}"
        )


def load_item_data(item_type: str, item_id: str) -> Dict[str, Any]:
    """Load the full data for a specific item."""
    store_path = get_store_components_path()
    
    if item_type.lower() == "flow":
        item_path = store_path / "flows"
    elif item_type.lower() == "component":
        item_path = store_path / "components"
    else:
        raise HTTPException(
            status_code=400,
            detail="Invalid item type. Must be 'flow' or 'component'."
        )
    
    # Find the file with the matching ID
    for file_path in item_path.glob(f"{item_id}_*.json"):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to load item data: {str(e)}"
            )
    
    raise HTTPException(
        status_code=404,
        detail=f"Item with ID {item_id} not found."
    )


@router.get("/", response_model=StoreData)
async def get_store_data(
    search: Optional[str] = Query(None, description="Search term for filtering items"),
    item_type: Optional[str] = Query(None, description="Filter by type: 'flow' or 'component'"),
    sort_by: Optional[str] = Query("popular", description="Sort by: 'popular', 'recent', 'alphabetical', 'downloads'"),
    limit: Optional[int] = Query(None, description="Limit the number of results"),
    offset: Optional[int] = Query(0, description="Offset for pagination")
) -> StoreData:
    """
    Get the main store data with optional filtering and sorting.

    Returns all flows and components from the AxieStudio Store.
    """
    try:
        store_data = load_store_index()
        
        # Combine flows and components for filtering
        all_items = store_data.flows + store_data.components
        
        # Apply search filter
        if search:
            search_lower = search.lower()
            filtered_items = []
            for item in all_items:
                if (search_lower in item.name.lower() or 
                    search_lower in item.description.lower() or
                    search_lower in item.author.username.lower() or
                    any(search_lower in tag.tags_id.get("name", "").lower() for tag in item.tags)):
                    filtered_items.append(item)
            all_items = filtered_items
        
        # Apply type filter
        if item_type:
            if item_type.lower() == "flow":
                all_items = [item for item in all_items if item.type == "FLOW"]
            elif item_type.lower() == "component":
                all_items = [item for item in all_items if item.type == "COMPONENT"]
        
        # Apply sorting
        if sort_by == "popular":
            all_items.sort(key=lambda x: x.stats.likes + x.stats.downloads, reverse=True)
        elif sort_by == "recent":
            all_items.sort(key=lambda x: x.dates.updated, reverse=True)
        elif sort_by == "downloads":
            all_items.sort(key=lambda x: x.stats.downloads, reverse=True)
        elif sort_by == "alphabetical":
            all_items.sort(key=lambda x: x.name.lower())
        
        # Apply pagination
        if limit:
            end_index = offset + limit
            all_items = all_items[offset:end_index]
        elif offset > 0:
            all_items = all_items[offset:]
        
        # Separate back into flows and components
        flows = [item for item in all_items if item.type == "FLOW"]
        components = [item for item in all_items if item.type == "COMPONENT"]
        
        # Update the response with filtered data
        store_data.flows = flows
        store_data.components = components
        
        return store_data
        
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve store data: {str(e)}"
        )


@router.get("/flows", response_model=List[StoreItem])
async def get_flows(
    search: Optional[str] = Query(None, description="Search term for filtering flows"),
    sort_by: Optional[str] = Query("popular", description="Sort by: 'popular', 'recent', 'alphabetical', 'downloads'"),
    limit: Optional[int] = Query(None, description="Limit the number of results"),
    offset: Optional[int] = Query(0, description="Offset for pagination")
) -> List[StoreItem]:
    """Get all flows from the store."""
    store_data = await get_store_data(search=search, item_type="flow", sort_by=sort_by, limit=limit, offset=offset)
    return store_data.flows


@router.get("/components", response_model=List[StoreItem])
async def get_components(
    search: Optional[str] = Query(None, description="Search term for filtering components"),
    sort_by: Optional[str] = Query("popular", description="Sort by: 'popular', 'recent', 'alphabetical', 'downloads'"),
    limit: Optional[int] = Query(None, description="Limit the number of results"),
    offset: Optional[int] = Query(0, description="Offset for pagination")
) -> List[StoreItem]:
    """Get all components from the store."""
    store_data = await get_store_data(search=search, item_type="component", sort_by=sort_by, limit=limit, offset=offset)
    return store_data.components


@router.get("/flow/{item_id}")
async def get_flow_data(item_id: str) -> Dict[str, Any]:
    """Get the full data for a specific flow."""
    return load_item_data("flow", item_id)


@router.get("/component/{item_id}")
async def get_component_data(item_id: str) -> Dict[str, Any]:
    """Get the full data for a specific component."""
    return load_item_data("component", item_id)


@router.get("/stats")
async def get_store_stats() -> Dict[str, Any]:
    """Get store statistics."""
    try:
        store_data = load_store_index()
        
        # Calculate additional stats
        total_downloads = sum(item.stats.downloads for item in store_data.flows + store_data.components)
        total_likes = sum(item.stats.likes for item in store_data.flows + store_data.components)
        
        # Get top authors
        author_stats = {}
        for item in store_data.flows + store_data.components:
            author = item.author.username
            if author not in author_stats:
                author_stats[author] = {"items": 0, "downloads": 0, "likes": 0}
            author_stats[author]["items"] += 1
            author_stats[author]["downloads"] += item.stats.downloads
            author_stats[author]["likes"] += item.stats.likes
        
        top_authors = sorted(author_stats.items(), key=lambda x: x[1]["items"], reverse=True)[:10]
        
        # Get tag statistics
        tag_stats = {}
        for item in store_data.flows + store_data.components:
            for tag in item.tags:
                tag_name = tag.tags_id.get("name", "")
                if tag_name:
                    tag_stats[tag_name] = tag_stats.get(tag_name, 0) + 1
        
        top_tags = sorted(tag_stats.items(), key=lambda x: x[1], reverse=True)[:20]
        
        return {
            "summary": store_data.summary,
            "conversion_info": store_data.conversion_info,
            "totals": {
                "total_downloads": total_downloads,
                "total_likes": total_likes,
                "total_items": store_data.summary.total_items,
                "total_flows": store_data.summary.total_flows,
                "total_components": store_data.summary.total_components
            },
            "top_authors": [{"username": author, **stats} for author, stats in top_authors],
            "top_tags": [{"name": tag, "count": count} for tag, count in top_tags]
        }
        
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve store statistics: {str(e)}"
        )
