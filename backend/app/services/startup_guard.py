"""Shared fail-fast checks for every production process."""

from sqlalchemy import text

from ..config import get_settings, validate_runtime_settings
from ..db import controller_engine, engine


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


async def validate_database_controller_role() -> None:
    """Require the Kubernetes reconciliation role to be non-superuser."""
    settings = get_settings()
    if settings.app_env.strip().lower() not in {"production", "prod"}:
        return
    if not settings.controller_database_url.strip():
        raise RuntimeError("CONTROLLER_DATABASE_URL is required for production controllers")
    try:
        async with controller_engine.connect() as connection:
            row = (await connection.execute(text(
                "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
            ))).first()
    except Exception as exc:
        raise RuntimeError("Unable to verify the production controller database role") from exc
    if not row:
        raise RuntimeError("Unable to verify the production controller database role")
    if bool(row[0]):
        raise RuntimeError("Production controller database role must not be a PostgreSQL superuser")
    if not bool(row[1]):
        raise RuntimeError("Production controller database role must have explicit BYPASSRLS permission")


async def validate_controller_startup() -> None:
    await validate_startup()
    await validate_database_controller_role()


async def validate_startup() -> None:
    """Run static and database-backed guards before a process serves work."""
    settings = get_settings()
    validate_runtime_settings(settings)
    await validate_database_runtime_role()
