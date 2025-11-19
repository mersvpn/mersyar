# FILE: database/engine.py (FINAL VERSION: OPTIMIZED & SELF-HEALING)

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .db_config import get_database_url
# Import Base correctly so create_all works
from database.models import Base 

LOGGER = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_async_session_maker: async_sessionmaker[AsyncSession] | None = None


async def init_db() -> None:
    """
    Initializes the database engine, session maker, performs auto-schema fixes,
    and creates performance indexes.
    """
    global _engine, _async_session_maker

    if _engine:
        LOGGER.info("Database engine is already initialized.")
        return

    try:
        db_url = get_database_url()

        # --- 🚀 PERFORMANCE OPTIMIZATION: CONNECTION POOLING ---
        _engine = create_async_engine(
            db_url,
            pool_recycle=3600,
            pool_pre_ping=True,
            echo=False,
            pool_size=20,       # نگهداری 20 اتصال باز برای پاسخگویی سریع
            max_overflow=10     # اجازه ساخت 10 اتصال اضافه در زمان شلوغی
        )
        # -------------------------------------------------------

        _async_session_maker = async_sessionmaker(
            bind=_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        
        # --- 🛠️ SMART DB MAINTENANCE BLOCK ---
        async with _engine.begin() as conn:
            
            # 1. SELF-HEALING: Check 'template_config' schema
            try:
                # Try to select the new column. If it fails, the schema is old.
                await conn.execute(text("SELECT panel_id FROM template_config LIMIT 0"))
            except Exception as e:
                # Check if the error is "Unknown column" (MySQL Error 1054)
                if "1054" in str(e) or "Unknown column" in str(e):
                    LOGGER.warning("⚠️ Outdated 'template_config' table detected. Dropping it to force update...")
                    await conn.execute(text("DROP TABLE IF EXISTS template_config"))
            
            # 2. TABLE CREATION: Create all missing tables (or the one we just dropped)
            # We run this BEFORE indexing to ensure tables exist.
            await conn.run_sync(Base.metadata.create_all)

            # 3. 🚀 PERFORMANCE BOOST: Create Indexes Automatically
            # This runs after create_all, so tables definitely exist.
            indexes_to_create = [
                ("users", "idx_users_telegram_id", "telegram_id"),
                ("marzban_links", "idx_links_username", "marzban_username"),
                ("marzban_links", "idx_links_telegram_id", "telegram_user_id"),
                ("panel_credentials", "idx_panel_id", "id"),
                ("user_notes", "idx_notes_username", "marzban_username"),
                ("bot_managed_users", "idx_managed_username", "marzban_username")
            ]
            
            for table, idx_name, col in indexes_to_create:
                try:
                    await conn.execute(text(f"CREATE INDEX {idx_name} ON {table}({col})"))
                    LOGGER.info(f"🚀 Performance Index '{idx_name}' created successfully.")
                except Exception as e:
                    # Error 1061: Duplicate key name (Index already exists) -> Ignore
                    # Error 1050: Table already exists (Generic) -> Ignore
                    if "1061" in str(e) or "Duplicate key" in str(e):
                        pass 
                    else:
                        # Log other errors as warnings but don't crash
                        LOGGER.debug(f"Index check for {idx_name}: {e}")

        # -------------------------------------------------------

        LOGGER.info("SQLAlchemy async engine created, schema verified, and indexes optimized.")
    
    except ValueError as ve:
        LOGGER.warning(f"Skipping SQLAlchemy engine creation: {ve}")
        _engine = None
        _async_session_maker = None
    except Exception as e:
        LOGGER.critical(f"Failed to create SQLAlchemy engine: {e}", exc_info=True)
        _engine = None
        _async_session_maker = None


async def close_db() -> None:
    """Closes the database engine connections."""
    global _engine
    if _engine:
        LOGGER.info("Closing SQLAlchemy engine connections.")
        await _engine.dispose()
        _engine = None


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Provides a transactional database session."""
    if _async_session_maker is None:
        await init_db()
        if _async_session_maker is None:
            raise ConnectionError("Database session maker is not initialized and failed to re-initialize.")

    async with _async_session_maker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()