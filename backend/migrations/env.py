from logging.config import fileConfig
import asyncio
import os

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.db import Base

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata


def run_migrations_offline():
    url = os.getenv("DATABASE_ADMIN_URL") or os.getenv("DATABASE_URL") or config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations():
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = os.getenv("DATABASE_ADMIN_URL") or os.getenv("DATABASE_URL") or configuration["sqlalchemy.url"]
    connectable = async_engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online():
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
