# FILE: database/crud/panel_credential.py (OPTIMIZED WITH CACHING)
import random
import logging
import time
from typing import List, Optional, Dict, Any
from sqlalchemy import update
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from ..models.template_config import TemplateConfig
from ..engine import get_session
from ..models.panel_credential import PanelCredential, PanelType

LOGGER = logging.getLogger(__name__)

# --- Caching Mechanism ---
_panel_cache: Optional[List[PanelCredential]] = None
_cache_timestamp: float = 0.0
CACHE_DURATION_SECONDS = 60  # Cache for 60 seconds (adjust as needed)

def _invalidate_cache():
    """Invalidates the panel cache."""
    global _panel_cache
    _panel_cache = None
    LOGGER.info("Panel cache has been invalidated.")

# --- CRUD Functions ---

async def add_panel(panel_data: Dict[str, Any]) -> Optional[PanelCredential]:
    """Adds a new panel to the database and invalidates the cache."""
    async with get_session() as session:
        try:
            new_panel = PanelCredential(
            name=panel_data['name'],
            panel_type=panel_data['panel_type'],
            api_url=panel_data['api_url'],
            username=panel_data['username'],
            password=panel_data['password']
        )
            session.add(new_panel)
            await session.commit()
            await session.refresh(new_panel)
            _invalidate_cache() # ✨ Invalidate cache on change
            return new_panel
        except Exception as e:
            await session.rollback()
            LOGGER.error(f"Failed to add new panel '{panel_data.get('name')}': {e}", exc_info=True)
            return None

# --- START: Replace the get_all_panels function in database/crud/panel_credential.py ---

async def get_all_panels(exclude_ids: Optional[List[int]] = None) -> List[PanelCredential]:
    print(f"!!!!!!!!!!!! GETTING ALL PANELS CALLED AT {time.time()} !!!!!!!!!!!!")
    """
    Retrieves all configured panels from the database, using a simple time-based cache.
    Can optionally exclude a list of panel IDs from the result.
    
    Args:
        exclude_ids (Optional[List[int]]): A list of panel IDs to exclude.
    """
    global _panel_cache, _cache_timestamp

    now = time.time()
    # Cache is only used when we are NOT excluding IDs, as that's the most common case.
    # If we need an excluded list, we fetch fresh to ensure accuracy.
    if exclude_ids is None and _panel_cache is not None and (now - _cache_timestamp) < CACHE_DURATION_SECONDS:
        LOGGER.debug("Returning cached panel list.")
        return _panel_cache

    if exclude_ids:
        LOGGER.info(f"Fetching fresh panel list from DB, excluding IDs: {exclude_ids}.")
    else:
        LOGGER.info("Fetching fresh panel list from DB and updating cache.")

    async with get_session() as session:
        stmt = select(PanelCredential).order_by(PanelCredential.name)
        
        # ✨ NEW: Add the exclusion logic to the SQLAlchemy statement
        if exclude_ids:
            stmt = stmt.where(PanelCredential.id.notin_(exclude_ids))
            
        result = await session.execute(stmt)
        panels = list(result.scalars().all())
        
        # Only update the cache if we fetched all panels without exclusion
        if exclude_ids is None:
            _panel_cache = panels
            _cache_timestamp = now
            
        return panels

# --- END: Replacement ---

async def get_panel_by_id(panel_id: int) -> Optional[PanelCredential]:
    """Retrieves a single panel by its ID. Uses the cache if available."""
    # Use the cache for faster lookups
    all_panels = await get_all_panels()
    for panel in all_panels:
        if panel.id == panel_id:
            return panel
    return None

async def delete_panel(panel_id: int) -> bool:
    """Deletes a panel by its ID and invalidates the cache."""
    async with get_session() as session:
        try:
            # Step 1: Delete the child row in `template_config` first.
            # This is non-blocking if no template config exists for this panel.
            await session.execute(
                delete(TemplateConfig).where(TemplateConfig.panel_id == panel_id)
            )

            # Step 2: Now, delete the parent row in `panel_credentials`.
            stmt = delete(PanelCredential).where(PanelCredential.id == panel_id)
            result = await session.execute(stmt)

            # Step 3: Commit the transaction.
            await session.commit()

            if result.rowcount > 0:
                _invalidate_cache()  # Invalidate cache on change
                LOGGER.info(f"Successfully deleted panel {panel_id} and its associated template config.")
                return True
            
            LOGGER.warning(f"Attempted to delete panel {panel_id}, but it was not found.")
            return False
            
        except Exception as e:
            await session.rollback()
            LOGGER.error(f"Failed to delete panel with ID {panel_id}: {e}", exc_info=True)
            return False
    # --- END: Replacement ---


async def toggle_test_panel_status(panel_id: int) -> Optional[bool]:
    """
    Toggles the is_test_panel status for a given panel.
    Returns the new status if successful, otherwise None.
    """
    async with get_session() as session:
        try:
            # First, get the current status
            panel = await session.get(PanelCredential, panel_id)
            if not panel:
                return None
            
            new_status = not panel.is_test_panel
            
            # Then, update it
            stmt = (
                update(PanelCredential)
                .where(PanelCredential.id == panel_id)
                .values(is_test_panel=new_status)
            )
            await session.execute(stmt)
            await session.commit()
            
            _invalidate_cache() # Invalidate cache as panel data has changed
            return new_status
        except Exception as e:
            await session.rollback()
            LOGGER.error(f"Failed to toggle test panel status for panel ID {panel_id}: {e}", exc_info=True)
            return None
# --- ADD THIS NEW FUNCTION to database/crud/panel_credential.py ---

async def get_panel_by_name(name: str) -> Optional[PanelCredential]:
    """Retrieves a single panel by its unique name."""
    async with get_session() as session:
        stmt = select(PanelCredential).where(PanelCredential.name == name)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
async def get_active_test_panels() -> List[PanelCredential]:
    """Retrieves all panels that are marked as active for test accounts."""
    async with get_session() as session:
        stmt = select(PanelCredential).where(PanelCredential.is_test_panel == True)
        result = await session.execute(stmt)
        return list(result.scalars().all())