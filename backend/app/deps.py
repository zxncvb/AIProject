from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import AdminSessionLocal, get_db, set_tenant_context
from .models import ApiKey, Membership, Role, Tenant, User
from .security import decode_access_token
from .services.auth_sessions import is_token_revoked


bearer = HTTPBearer(auto_error=False)

ROLE_PERMISSIONS = {
    "owner": {"workspace.read", "workflow.write", "workflow.run", "knowledge.write", "model.admin", "extension.admin", "member.admin", "audit.read"},
    "admin": {"workspace.read", "workflow.write", "workflow.run", "knowledge.write", "model.admin", "extension.admin", "audit.read"},
    "developer": {"workspace.read", "workflow.write", "workflow.run", "knowledge.write"},
    "editor": {"workspace.read", "workflow.write", "workflow.run", "knowledge.write"},
    "operator": {"workspace.read", "workflow.run", "audit.read"},
    "viewer": {"workspace.read", "audit.read"},
}


@dataclass
class RequestContext:
    user: User
    tenant: Tenant
    membership: Membership
    custom_permissions: tuple[str, ...] = ()

    @property
    def user_id(self) -> str:
        return self.user.id

    @property
    def tenant_id(self) -> str:
        return self.tenant.id

    @property
    def role(self) -> str:
        return self.membership.role

    @property
    def permissions(self) -> set[str]:
        return ROLE_PERMISSIONS.get(self.role, set()) | set(self.custom_permissions)


async def get_context(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
    x_tenant_id: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header()] = None,
) -> RequestContext:
    token = x_api_key or (credentials.credentials if credentials else None) or request.cookies.get("eai_access_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="需要登录")
    api_key_row = None
    try:
        claims = decode_access_token(token)
        if await is_token_revoked(claims):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录会话已失效")
        user_id = str(claims["sub"])
        token_tenant = str(claims["tenant_id"])
        tenant_id = x_tenant_id or token_tenant
        await set_tenant_context(db, tenant_id)
        result = await db.execute(
            select(User, Tenant, Membership)
            .join(Membership, (Membership.user_id == User.id) & (Membership.is_active.is_(True)))
            .join(Tenant, Tenant.id == Membership.tenant_id)
            .where(User.id == user_id, Tenant.id == tenant_id, User.is_active.is_(True), Tenant.is_active.is_(True))
        )
        row = result.first()
    except Exception:
        key_hash = hashlib.sha256(token.encode()).hexdigest()
        # API keys do not expose a tenant identifier. Resolve only the hashed key
        # through the privileged connection, then perform the actual authorization
        # through the tenant-scoped runtime connection so RLS remains effective.
        async with AdminSessionLocal() as admin_db:
            key_identity = await admin_db.scalar(select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.enabled.is_(True)))
        if not key_identity:
            raise HTTPException(status_code=401, detail="登录令牌无效或已过期")
        tenant_id = key_identity.tenant_id
        await set_tenant_context(db, tenant_id)
        result = await db.execute(
            select(User, Tenant, Membership, ApiKey)
            .join(ApiKey, ApiKey.user_id == User.id)
            .join(Membership, (Membership.user_id == User.id) & (Membership.tenant_id == ApiKey.tenant_id) & (Membership.is_active.is_(True)))
            .join(Tenant, Tenant.id == ApiKey.tenant_id)
            .where(ApiKey.key_hash == key_hash, ApiKey.enabled.is_(True), User.is_active.is_(True), Tenant.is_active.is_(True))
        )
        api_key_row = result.first()
        if not api_key_row:
            raise HTTPException(status_code=401, detail="登录令牌无效或已过期")
        row = api_key_row[:3]
        if api_key_row[3].expires_at and api_key_row[3].expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="API Key 已过期")
        api_key_row[3].last_used_at = datetime.now(timezone.utc)
        await db.commit()
        await set_tenant_context(db, tenant_id)
    if not row:
        raise HTTPException(status_code=403, detail="用户不属于该租户")
    custom_permissions: tuple[str, ...] = ()
    if row[2].custom_role_id:
        role = await db.scalar(select(Role).where(Role.id == row[2].custom_role_id, Role.tenant_id == tenant_id))
        if role:
            custom_permissions = tuple(role.permissions_json or [])
    if api_key_row:
        custom_permissions = (*custom_permissions, *(f"api:{scope}" for scope in (api_key_row[3].scopes_json or [])))
    request.state.tenant_id = tenant_id
    request.state.user_id = row[0].id
    return RequestContext(user=row[0], tenant=row[1], membership=row[2], custom_permissions=custom_permissions)


def require_roles(*roles: str):
    async def dependency(ctx: Annotated[RequestContext, Depends(get_context)]) -> RequestContext:
        if ctx.role not in roles and not any(ROLE_PERMISSIONS.get(role, set()).issubset(ctx.permissions) for role in roles):
            raise HTTPException(status_code=403, detail=f"需要以下角色之一: {', '.join(roles)}")
        return ctx

    return dependency


def require_permission(permission: str):
    async def dependency(ctx: Annotated[RequestContext, Depends(get_context)]) -> RequestContext:
        if permission not in ctx.permissions:
            raise HTTPException(status_code=403, detail=f"缺少权限: {permission}")
        return ctx

    return dependency


Context = Annotated[RequestContext, Depends(get_context)]
EditorContext = Annotated[RequestContext, Depends(require_roles("owner", "admin", "developer", "editor"))]
OperatorContext = Annotated[RequestContext, Depends(require_roles("owner", "admin", "developer", "editor", "operator"))]
AdminContext = Annotated[RequestContext, Depends(require_roles("owner", "admin"))]
PermissionAdminContext = Annotated[RequestContext, Depends(require_permission("member.admin"))]
