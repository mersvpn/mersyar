# alembic/env.py (FINAL CORRECTED VERSION)

import os
import sys
from logging.config import fileConfig

# --- START OF MODIFICATIONS ---

# 1. Add project root to Python's path so we can import our modules
sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), '..')))

# 2. Import and call load_dotenv with an explicit path
from dotenv import load_dotenv
project_root = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
dotenv_path = os.path.join(project_root, '.env')
load_dotenv(dotenv_path=dotenv_path)

# 3. Now we can safely import our project modules
from database.models import Base
from database.db_config import get_sync_database_url

# --- END OF MODIFICATIONS ---


from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# --- MODIFICATION: Point to our Base metadata ---
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.
    This is less commonly used.
    """
    # --- MODIFICATION: Use our dynamic URL function ---
    url = get_sync_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.
    This is the primary mode for applying migrations.
    """
    # --- MODIFICATION: Dynamically set the database URL from .env ---
    configuration = config.get_section(config.config_ini_section)
    configuration['sqlalchemy.url'] = get_sync_database_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()