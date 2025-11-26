# --- START OF FILE database/crud/bot_managed_user.py ---
import logging
from typing import List

from sqlalchemy import select, delete, union
from sqlalchemy.dialects.mysql import insert as mysql_insert

from ..engine import get_session
from ..models.bot_managed_user import BotManagedUser
from ..models.marzban_link import MarzbanTelegramLink

LOGGER = logging.getLogger(__name__)


async def get_all_managed_users() -> List[str]:
    """Retrieves a list of all usernames managed by the bot."""
    async with get_session() as session:
        stmt = select(BotManagedUser.marzban_username)
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def add_to_managed_list(marzban_username: str, created_by_admin_id: int = None) -> bool:
    """Adds a username to the bot-managed list with creator ID."""
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
    """
    Optimized version: Retrieves all related users in a SINGLE database query.
    """
    async with get_session() as session:
        created_subq = select(BotManagedUser.marzban_username).where(
            BotManagedUser.created_by_admin_id == admin_id
        )

        customers_subq = select(MarzbanTelegramLink.telegram_user_id).where(
            MarzbanTelegramLink.marzban_username.in_(created_subq)
        )

        siblings_query = select(MarzbanTelegramLink.marzban_username).where(
            MarzbanTelegramLink.telegram_user_id.in_(customers_subq)
        )

        final_stmt = union(siblings_query, created_subq)

        result = await session.execute(final_stmt)
        return list(result.scalars().all())
    

async def get_owner_of_user(marzban_username: str) -> int | None:
    """
    Returns the telegram ID of the admin who created this user.
    Returns None if not found or created by system.
    """
    async with get_session() as session:
        stmt = select(BotManagedUser.created_by_admin_id).where(BotManagedUser.marzban_username == marzban_username)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()