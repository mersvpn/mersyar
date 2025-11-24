# --- START OF FILE database/crud/bot_setting.py ---
import json
import logging
from typing import Any, Dict, Optional

from sqlalchemy import select, delete, insert
from sqlalchemy.dialects.mysql import insert as mysql_insert

from ..engine import get_session
from ..models.bot_setting import BotSetting

LOGGER = logging.getLogger(__name__)

_bot_settings_cache: Optional[Dict[str, Any]] = None


def _invalidate_cache():
    """Clears the in-memory cache for bot settings."""
    global _bot_settings_cache
    _bot_settings_cache = None
    LOGGER.info("Bot settings cache invalidated.")


async def load_bot_settings() -> Dict[str, Any]:
    """
    Loads all bot settings from the database.
    Uses an in-memory cache to avoid frequent database reads.
    """
    global _bot_settings_cache
    if _bot_settings_cache is not None:
        return _bot_settings_cache.copy()

    settings = {}
    async with get_session() as session:
        result = await session.execute(select(BotSetting))
        all_settings = result.scalars().all()

        for setting in all_settings:
            try:
                # Attempt to decode as JSON for complex types
                settings[setting.setting_key] = json.loads(setting.setting_value)
            except (json.JSONDecodeError, TypeError):
                # Fallback to raw string value
                settings[setting.setting_key] = setting.setting_value
    
    _bot_settings_cache = settings
    LOGGER.info("Bot settings loaded from DB and cached.")
    return _bot_settings_cache.copy()


async def save_bot_settings(settings_to_update: Dict[str, Any]) -> bool:
    """
    Saves or updates multiple settings in the bot_settings table.
    Uses an INSERT ... ON DUPLICATE KEY UPDATE statement for efficiency.
    ✨ FIX: Directly updates the cache upon successful save to ensure consistency.
    """
    global _bot_settings_cache
    if not settings_to_update:
        return True

    values_to_insert = []
    for key, value in settings_to_update.items():

        if isinstance(value, (dict, list, bool)):
            value_to_save = json.dumps(value)
        else:
            value_to_save = str(value)
        # -----------------------------------------------------
        
        values_to_insert.append({"setting_key": key, "setting_value": value_to_save})

    if not values_to_insert:
        return False

    stmt = mysql_insert(BotSetting).values(values_to_insert)
    update_stmt = stmt.on_duplicate_key_update(
        setting_value=stmt.inserted.setting_value
    )
    
    async with get_session() as session:
        try:
            await session.execute(update_stmt)
            await session.commit()
            
            if _bot_settings_cache is not None:
                _bot_settings_cache.update(settings_to_update)
                LOGGER.info(f"Bot settings cache updated with: {list(settings_to_update.keys())}")
            else:
                _invalidate_cache()

            return True
        except Exception as e:
            await session.rollback()
            LOGGER.error(f"Failed to save bot settings: {e}", exc_info=True)
            return False