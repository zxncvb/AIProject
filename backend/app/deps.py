from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_db, set_tenant_context
from .models import Membership, Role, Tenant, User
from .security import decode_access_token


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
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
    x_tenant_id: Annotated[str | None, Header()] = None,
) -> RequestContext:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="需要登录")
    try:
        claims = decode_access_token(credentials.credentials)
        user_id = str(claims["sub"])
        token_tenant = str(claims["tenant_id"])
    except Exception as exc:
        raise HTTPException(status_code=401, detail="登录令牌无效或已过期") from exc
    tenant_id = x_tenant_id or token_tenant
    await set_tenant_context(db, tenant_id)
    result = await db.execute(
        select(User, Tenant, Membership)
        .join(Membership, Membership.user_id == User.id)
        .join(Tenant, Tenant.id == Membership.tenant_id)
        .where(User.id == user_id, Tenant.id == tenant_id, User.is_active.is_(True), Tenant.is_active.is_(True))
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=403, detail="用户不属于该租户")
    custom_permissions: tuple[str, ...] = ()
    if row[2].custom_role_id:
        role = await db.scalar(select(Role).where(Role.id == row[2].custom_role_id, Role.tenant_id == tenant_id))
        if role:
            custom_permissions = tuple(role.permissions_json or [])
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
