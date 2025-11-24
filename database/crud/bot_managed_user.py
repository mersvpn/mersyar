# --- START OF FILE database/crud/bot_managed_user.py ---
import logging
from typing import List

from sqlalchemy import select, delete
from sqlalchemy.dialects.mysql import insert as mysql_insert

from ..engine import get_session
from ..models.bot_managed_user import BotManagedUser

LOGGER = logging.getLogger(__name__)


async def get_all_managed_users() -> List[str]:
    """Retrieves a list of all usernames managed by the bot."""
    async with get_session() as session:
        stmt = select(BotManagedUser.marzban_username)
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def add_to_managed_list(marzban_username: str, created_by_admin_id: int = None) -> bool:
    """Adds a username to the bot-managed list with creator ID."""
    # مقدار دهی ستون جدید در اینجا انجام می‌شود 👇
    stmt = mysql_insert(BotManagedUser).values(
        marzban_username=marzban_username,
        created_by_admin_id=created_by_admin_id
    ).prefix_with("IGNORE")
    
    async with get_session() as session:
        try:
            await session.execute(stmt)
            await session.commit()
            return True
        except Exception as e:
            await session.rollback()
            LOGGER.error(f"Failed to add '{marzban_username}' to managed list: {e}", exc_info=True)
            return False


async def remove_from_managed_list(marzban_username: str) -> bool:
    """Removes a username from the bot-managed list."""
    async with get_session() as session:
        try:
            stmt = delete(BotManagedUser).where(BotManagedUser.marzban_username == marzban_username)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0
        except Exception as e:
            await session.rollback()
            LOGGER.error(f"Failed to remove '{marzban_username}' from managed list: {e}", exc_info=True)
            return False
        
async def get_users_created_by(admin_id: int) -> List[str]:
    """Returns a list of usernames created by a specific admin."""
    async with get_session() as session:
        stmt = select(BotManagedUser.marzban_username).where(BotManagedUser.created_by_admin_id == admin_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())

# --- END OF FILE database/crud/bot_managed_user.py ---