# FILE: core/helpers.py

import logging
from typing import Optional, Dict, Any

# --- Absolute imports from other parts of the project ---
from database.models.panel_credential import PanelCredential
from database.crud import panel_credential as crud_panel

# --- Absolute imports for panel API classes ---
from core.panel_api.base import PanelAPI
from core.panel_api.marzban import MarzbanPanel
from core.panel_api.xui import XUIPanel

LOGGER = logging.getLogger(__name__)


async def get_api_for_panel(panel: PanelCredential) -> Optional[PanelAPI]:
    """
    Main factory to create an API object from a panel database object.
    This is the central point for handling different panel types.
    """
    if not panel:
        return None

    credentials = {
        'api_url': panel.api_url,
        'username': panel.username,
        'password': panel.password
    }

    if panel.panel_type.value == "marzban":
        return MarzbanPanel(credentials)
    
    elif panel.panel_type.value == "x-ui":
        return XUIPanel(credentials)
        
    # In the future, you can add other panel types here:
    # elif panel.panel_type.value == "pasargad":
    #     from core.panel_api.pasargad import PasargadPanel
    #     return PasargadPanel(credentials)

    LOGGER.warning(f"Attempted to create an API object for an unsupported panel type: '{panel.panel_type.value}'")
    return None


async def get_api_for_panel_by_id(panel_id: int) -> Optional[PanelAPI]:
    """
    A convenient wrapper to get a panel from DB by its ID and create an API object for it.
    """
    panel = await crud_panel.get_panel_by_id(panel_id)
    if not panel:
        LOGGER.error(f"Could not find panel with ID: {panel_id}")
        return None
    return await get_api_for_panel(panel)