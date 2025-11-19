# در بالای shared/panel_utils.py
import logging
import asyncio
from typing import List, Dict, Any, Optional
from core.panel_api.base import PanelAPI
from core.panel_api.marzban import MarzbanPanel
from database.crud import panel_credential as crud_panel
from database.models.panel_credential import PanelType

LOGGER = logging.getLogger(__name__)



async def _get_api_for_panel(panel) -> Optional[PanelAPI]:
    """Factory to create an API object from a panel DB object."""
    if panel.panel_type == PanelType.MARZBAN:
        credentials = {'api_url': panel.api_url, 'username': panel.username, 'password': panel.password}
        return MarzbanPanel(credentials)
    return None

# --- START: Replace this function in shared/panel_utils.py ---

async def get_all_users_from_all_panels() -> List[Dict[str, Any]]:
    """Fetches and aggregates users from all configured panels in parallel."""
    import asyncio
    LOGGER.info("[Panel Utils] Starting to fetch users from all panels...")
    
    all_panels = await crud_panel.get_all_panels()
    if not all_panels:
        LOGGER.warning("[Panel Utils] No panels configured in DB. Returning empty list.")
        return []

    async def fetch_users_from_panel(panel):
        """Helper coroutine to fetch users from a single panel."""
        LOGGER.info(f"[Panel Utils] -> Fetching users for panel '{panel.name}'...")
        try:
            api = await _get_api_for_panel(panel)
            if not api: 
                LOGGER.warning(f"[Panel Utils] -> Could not create API for panel '{panel.name}'. Skipping.")
                return []
            
            users = await api.get_all_users()
            if users:
                LOGGER.info(f"[Panel Utils] -> Successfully fetched {len(users)} users from '{panel.name}'.")
                for user in users:
                    user['panel_name'] = panel.name
                    user['panel_id'] = panel.id
                return users
            else:
                # This could mean 0 users, or an API error that returned None/[]
                LOGGER.warning(f"[Panel Utils] -> Received no users or an empty list from '{panel.name}'.")
                return []
        except Exception as e:
            LOGGER.error(f"[Panel Utils] -> CRITICAL ERROR while fetching from panel '{panel.name}': {e}", exc_info=True)
            return [] # Return empty list on failure to not break the whole process

    tasks = [fetch_users_from_panel(panel) for panel in all_panels]
    
    LOGGER.info(f"[Panel Utils] Awaiting {len(tasks)} panel tasks to complete...")
    results_of_lists = await asyncio.gather(*tasks)
    
    aggregated_users = [user for user_list in results_of_lists for user in user_list]
    LOGGER.info(f"[Panel Utils] Finished fetching. Aggregated a total of {len(aggregated_users)} users from {len(all_panels)} panel(s).")
    
    return aggregated_users

# --- END: Replacement ---

async def get_user_data_from_panels(username: str, panel_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """
    Finds a specific user.
    If panel_id is provided, it searches only in that panel.
    Otherwise, it searches across all panels.
    """
    if panel_id:
        # Search in a specific panel
        panel = await crud_panel.get_panel_by_id(panel_id)
        if not panel:
            LOGGER.warning(f"get_user_data requested for non-existent panel_id: {panel_id}")
            return None
        
        api = await _get_api_for_panel(panel)
        if not api: return None

        user_data = await api.get_user_data(username)
        if user_data:
            user_data['panel_name'] = panel.name
            user_data['panel_id'] = panel.id
            return user_data
    else:
        # Search across all panels (original behavior)
        all_panels = await crud_panel.get_all_panels()
        for panel in all_panels:
            api = await _get_api_for_panel(panel)
            if not api: continue
            user_data = await api.get_user_data(username)
            if user_data:
                user_data['panel_name'] = panel.name
                user_data['panel_id'] = panel.id
                return user_data
    
    return None
# --- END: Replacement ---