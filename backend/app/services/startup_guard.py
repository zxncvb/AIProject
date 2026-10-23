"""Shared fail-fast checks for every production process."""

from sqlalchemy import text

from ..config import get_settings, validate_runtime_settings
from ..db import engine


async def validate_database_runtime_role() -> None:
    """Reject a PostgreSQL superuser as the application's runtime account."""
    settings = get_settings()
    if settings.app_env.strip().lower() not in {"production", "prod"}:
        return
    try:
        async with engine.connect() as connection:
            is_superuser = await connection.scalar(
                text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
            )
    except Exception as exc:
        raise RuntimeError("Unable to verify that the production runtime database role is non-superuser") from exc
    if is_superuser is None:
        raise RuntimeError("Unable to verify that the production runtime database role is non-superuser")
    if bool(is_superuser):
        raise RuntimeError("Production runtime database role must not be a PostgreSQL superuser")


async def validate_startup() -> None:
    """Run static and database-backed guards before a process serves work."""
    settings = get_settings()
    validate_runtime_settings(settings)
    await validate_database_runtime_role()
