# FILE: database/crud/admin.py

from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError
from database.engine import get_session as get_async_session
from database.models.admin import Admin
import logging

LOGGER = logging.getLogger(__name__)

async def add_admin(user_id: int, username: str = None, promoted_by: str = "System") -> bool:
    """
    Promotes a user to support admin.
    Returns True if successful, False if already exists or error.
    """
    async with get_async_session() as session:
        try:
            new_admin = Admin(user_id=user_id, username=username, promoted_by=promoted_by)
            session.add(new_admin)
            await session.commit()
            return True
        except IntegrityError:
            await session.rollback()
            return False # User is already an admin
        except Exception as e:
            LOGGER.error(f"Error adding admin {user_id}: {e}")
            await session.rollback()
            return False

async def remove_admin(user_id: int) -> bool:
    """Removes a user from support admins."""
    async with get_async_session() as session:
        try:
            stmt = delete(Admin).where(Admin.user_id == user_id)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0
        except Exception as e:
            LOGGER.error(f"Error removing admin {user_id}: {e}")
            return False

async def get_all_admins():
    """Returns a list of all support admins."""
    async with get_async_session() as session:
        result = await session.execute(select(Admin))
        return result.scalars().all()

async def is_support_admin(user_id: int) -> bool:
    """Checks if a user is a support admin in the database."""
    async with get_async_session() as session:
        result = await session.execute(select(Admin).where(Admin.user_id == user_id))
        return result.scalar_one_or_none() is not None