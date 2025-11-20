import importlib
from pathlib import Path

from sqlmodel import SQLModel

from alembic import context

from app.core.config import config as app_config
from app.core.db import engine
from app.core.logging import setup_logging


# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Use our logging configuration
setup_logging()

# Set the database URL from the application config
config.set_main_option("sqlalchemy.url", app_config.db_url)

# Dynamically import all models to ensure they are registered with SQLModel.metadata
models_dir = Path(__file__).parent.parent / "app" / "models"
for f in models_dir.glob("*.py"):
    module_name = f.stem
    importlib.import_module(f"app.models.{module_name}")
target_metadata = SQLModel.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
