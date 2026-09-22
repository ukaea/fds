from sqlalchemy import create_engine
from sqlmodel import SQLModel

# Imported for its side effect: registers every table with SQLModel.metadata.
import app.models  # noqa: F401
from alembic import context
from app.core.config import config as app_config
from app.core.logging import setup_logging

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Use our logging configuration
setup_logging()

# The application's database, unless a caller has already named one: the tests
# point migrations at a throwaway database this way.
if not config.get_main_option("sqlalchemy.url", ""):
    config.set_main_option("sqlalchemy.url", app_config.db_url)

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
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    The engine is built from the URL in the Alembic config rather than the
    application's, so a caller can point a migration run at another database by
    setting ``sqlalchemy.url`` (which is what the tests do).
    """
    connectable = create_engine(config.get_main_option("sqlalchemy.url", ""))

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
