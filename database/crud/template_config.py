# --- START: Replace entire file database/crud/template_config.py ---
import logging
from typing import Dict, Any, Optional

from sqlalchemy import select, delete
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.exc import IntegrityError

from ..engine import get_session
from ..models.template_config import TemplateConfig

LOGGER = logging.getLogger(__name__)


async def load_template_config(panel_id: int) -> Optional[TemplateConfig]:
    """
    Loads the template config for a specific panel from the database.
    """
    async with get_session() as session:
        result = await session.execute(
            select(TemplateConfig).where(TemplateConfig.panel_id == panel_id)
        )
        return result.scalar_one_or_none()


async def save_template_config(panel_id: int, config_data: Dict[str, Any]) -> bool:
    """
    Saves or updates the template config for a specific panel.
    It first tries to delete any existing config for the panel, then inserts the new one.
    This approach is simpler and safer than ON DUPLICATE KEY UPDATE with a composite key.
    """
    async with get_session() as session:
        try:
            # First, delete any existing template for this panel to ensure a clean slate.
            await session.execute(
                delete(TemplateConfig).where(TemplateConfig.panel_id == panel_id)
            )

            # Now, insert the new template configuration.
            new_config = TemplateConfig(
                panel_id=panel_id,
                template_username=config_data["template_username"],
                proxies=config_data.get("proxies"),
                inbounds=config_data.get("inbounds")
            )
            session.add(new_config)
            
            await session.commit()
            LOGGER.info(f"Successfully saved template config for panel_id: {panel_id}")
            return True
        except IntegrityError as e:
            # This might happen if the panel_id doesn't exist in the parent table.
            await session.rollback()
            LOGGER.error(f"IntegrityError saving template for panel_id {panel_id}. Does the panel exist? Error: {e}")
            return False
        except Exception as e:
            await session.rollback()
            LOGGER.error(f"Failed to save template config for panel_id {panel_id}: {e}", exc_info=True)
            return False

# --- END: Replacement ---