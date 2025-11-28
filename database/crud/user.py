# --- START OF FILE database/crud/user.py ---

import logging
from decimal import Decimal
from typing import List, Optional
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from telegram import User as TelegramUser
from config import config

from ..engine import get_session
from ..models.user import User
from ..models.marzban_link import MarzbanTelegramLink


LOGGER = logging.getLogger(__name__)


async def get_user_by_id(user_id: int) -> Optional[User]:
    async with get_session() as session:
        return await session.get(User, user_id)


async def add_or_update_user(tg_user: TelegramUser) -> bool:
    is_new_user = False
    try:
        async with get_session() as session:
            db_user = await session.get(User, tg_user.id)

            if db_user:
                db_user.first_name = tg_user.first_name
                db_user.username = tg_user.username
            else:
                is_new_user = True
                db_user = User(
                    user_id=tg_user.id,
                    first_name=tg_user.first_name,
                    username=tg_user.username,
                )
            session.add(db_user)
            await session.commit()
            
    except Exception as e:
        LOGGER.error(f"Database operation failed for user {tg_user.id}: {e}", exc_info=True)
        return False

    return is_new_user


async def get_user_wallet_balance(user_id: int) -> Optional[Decimal]:
    async with get_session() as session:
        user = await session.get(User, user_id)
        if user:
            return user.wallet_balance
    LOGGER.warning(f"Could not retrieve wallet balance for non-existent user_id: {user_id}.")
    return None


async def increase_wallet_balance(user_id: int, amount: Decimal | float) -> Optional[Decimal]:
    if not isinstance(amount, Decimal):
        amount = Decimal(str(amount))

    if amount <= 0:
        LOGGER.warning(f"Attempted to increase wallet with non-positive amount: {amount}")
        return None

    async with get_session() as session:
        user = await session.get(User, user_id)
        if user:
            user.wallet_balance += amount
            await session.commit()
            await session.refresh(user)
            return user.wallet_balance
    LOGGER.error(f"Failed to increase balance for non-existent user_id: {user_id}")
    return None


async def decrease_wallet_balance(user_id: int, amount: Decimal | float) -> Optional[Decimal]:
    if not isinstance(amount, Decimal):
        amount = Decimal(str(amount))

    if amount <= 0:
        LOGGER.warning(f"Attempted to decrease wallet with non-positive amount: {amount}")
        return None

    async with get_session() as session:
        user = await session.get(User, user_id)
        if user:
            if user.wallet_balance >= amount:
                user.wallet_balance -= amount
                await session.commit()
                await session.refresh(user)
                return user.wallet_balance
            else:
                LOGGER.warning(f"Insufficient funds for user {user_id} to decrease by {amount}.")
                return None
    LOGGER.error(f"Failed to decrease balance for non-existent user_id: {user_id}")
    return None


async def get_user_by_marzban_username(marzban_username: str) -> Optional[User]:
    async with get_session() as session:
        stmt = (
            select(User)
            .join(MarzbanTelegramLink)
            .where(MarzbanTelegramLink.marzban_username == marzban_username)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


async def get_user_test_account_count(user_id: int) -> int:
    async with get_session() as session:
        user = await session.get(User, user_id)
        return user.test_accounts_received if user else 0


async def increment_user_test_account_count(user_id: int) -> bool:
    async with get_session() as session:
        user = await session.get(User, user_id)
        if user:
            user.test_accounts_received += 1
            await session.commit()
            return True
    return False


async def get_all_user_ids() -> List[int]:
    async with get_session() as session:
        admin_ids = tuple(config.AUTHORIZED_USER_IDS)
        stmt = select(User.user_id)
        if admin_ids:
            stmt = stmt.where(User.user_id.not_in(admin_ids))
        
        result = await session.execute(stmt)
        return list(result.scalars().all())
    
async def get_total_users_count() -> int:
    """Returns the total number of users in the users table."""
    async with get_session() as session:
        result = await session.execute(select(func.count(User.user_id)))
        return result.scalar_one()
    
async def update_user_note(user_id: int, note: Optional[str]) -> bool:
    async with get_session() as session:
        try:
            result = await session.execute(
                select(User).where(User.user_id == user_id)
            )
            user = result.scalar_one_or_none()
            if user:
                user.admin_note = note
                await session.commit()
                return True
            return False
        except Exception as e:
            await session.rollback()
            LOGGER.error(f"Failed to update user note for {user_id}: {e}")
            return False

async def update_last_activity(user_id: int) -> bool:
    async with get_session() as session:
        try:
            result = await session.execute(
                select(User).where(User.user_id == user_id)
            )
            user = result.scalar_one_or_none()
            if user:
                user.last_activity = datetime.now()
                await session.commit()
                return True
            return False
        except Exception as e:
            await session.rollback()
            LOGGER.error(f"Failed to update last activity for {user_id}: {e}")
            return False

async def get_user_with_relations(user_id: int) -> Optional[User]:
    async with get_session() as session:
        try:
            result = await session.execute(
                select(User)
                .options(selectinload(User.marzban_links))
                .options(selectinload(User.pending_invoices))
                .where(User.user_id == user_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            LOGGER.error(f"Failed to get user with relations: {e}")
            return None

# --- END OF FILE database/crud/user.py ---