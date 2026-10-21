from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def reject_corrupted_label(value: str) -> str:
    value = value.strip()
    if "�" in value or "???" in value or any(marker in value for marker in ("锟", "浼佷笟", "绠＄悊")):
        raise ValueError("显示名称包含乱码，请使用 UTF-8 重新提交")
    return value


class LoginRequest(BaseModel):
    email: str
    password: str
    tenant_slug: str | None = None
    mfa_code: str | None = Field(default=None, min_length=6, max_length=8)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=12, max_length=200)


class MFACodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class MFADisableRequest(BaseModel):
    current_password: str = Field(min_length=1)
    code: str = Field(min_length=6, max_length=8)


class ScimTokenCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class ScimUserCreate(BaseModel):
    userName: str = Field(min_length=3, max_length=320)
    displayName: str = Field(default="", max_length=120)
    active: bool = True
    roles: list[dict[str, Any]] = Field(default_factory=list)

    _validate_display_name = field_validator("displayName")(reject_corrupted_label)


class ScimUserPatch(BaseModel):
    Operations: list[dict[str, Any]] = Field(default_factory=list)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict[str, Any]
    tenant: dict[str, Any]


class OIDCStartRequest(BaseModel):
    tenant_slug: str | None = None


class OIDCCallbackRequest(BaseModel):
    code: str = Field(min_length=1)
    state: str = Field(min_length=16, max_length=256)


class LDAPLoginRequest(BaseModel):
    email: str
    password: str
    tenant_slug: str | None = None


class MemberCreate(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=12, max_length=200)
    display_name: str = Field(min_length=1, max_length=120)
    role: str = Field(default="viewer", pattern=r"^(owner|admin|developer|editor|operator|viewer)$")

    _validate_display_name = field_validator("display_name")(reject_corrupted_label)


class MemberRoleUpdate(BaseModel):
    role: str = Field(pattern=r"^(owner|admin|developer|editor|operator|viewer)$")
    custom_role_id: str | None = None
    is_active: bool | None = None


class ProjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,78}[a-z0-9]$", max_length=80)
    description: str = ""
    workspace_id: str | None = None


class ProviderCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    provider_type: str = "openai_compatible"
    base_url: str = "https://api.openai.com/v1"
    default_model: str = Field(min_length=1, max_length=160)
    api_key: str = ""
    config: dict[str, Any] = Field(default_factory=dict)


class AgentCreate(BaseModel):
    project_id: str
    name: str = Field(min_length=2, max_length=160)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,98}[a-z0-9]$", max_length=100)
    description: str = ""
    system_prompt: str = Field(min_length=1)
    provider_id: str | None = None
    knowledge_base_id: str | None = None
    workspace_id: str | None = None


class AgentChatRequest(BaseModel):
    message: str = Field(min_length=1)
    conversation: list[dict[str, str]] = Field(default_factory=list)
    cost_center: str | None = Field(default=None, max_length=120)


class WorkflowCreate(BaseModel):
    project_id: str
    name: str = Field(min_length=2, max_length=160)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,98}[a-z0-9]$", max_length=100)
    description: str = ""
    graph: dict[str, Any] = Field(default_factory=lambda: {"nodes": [], "edges": []})
    input_schema: dict[str, Any] = Field(default_factory=dict)
    changelog: str = "initial"


class WorkflowUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    slug: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9-]{1,98}[a-z0-9]$", max_length=100)
    description: str | None = Field(default=None, max_length=2000)


class WorkflowVersionCreate(BaseModel):
    graph: dict[str, Any]
    input_schema: dict[str, Any] = Field(default_factory=dict)
    changelog: str = ""


class WorkflowRunRequest(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)
    version: int | None = None
    environment: str = Field(default="production", pattern=r"^(dev|staging|production)$")
    cost_center: str | None = Field(default=None, max_length=120)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=120)


class WorkflowWebhookRequest(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)
    version: int | None = None


class ReleaseRequest(BaseModel):
    environment: str = Field(pattern=r"^(dev|staging|production)$")
    version: int | None = None
    traffic_percent: int = Field(default=100, ge=1, le=100)


class RollbackRequest(BaseModel):
    environment: str = Field(default="production", pattern=r"^(dev|staging|production)$")


class ScheduleCreate(BaseModel):
    interval_seconds: int = Field(ge=10, le=31_536_000)
    environment: str = Field(default="production", pattern=r"^(dev|staging|production)$")
    input: dict[str, Any] = Field(default_factory=dict)
    active: bool = True


class ScheduleUpdate(BaseModel):
    interval_seconds: int | None = Field(default=None, ge=10, le=31_536_000)
    active: bool | None = None
    input: dict[str, Any] | None = None


class ApplicationCreate(BaseModel):
    project_id: str
    name: str = Field(min_length=2, max_length=160)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,98}[a-z0-9]$", max_length=100)
    description: str = ""
    app_type: str = Field(default="low_code", pattern=r"^(low_code|full_code)$")
    runtime: dict[str, Any] = Field(default_factory=dict)
    source: dict[str, Any] = Field(default_factory=dict)


class ApplicationVersionCreate(BaseModel):
    source: dict[str, Any] = Field(default_factory=dict)
    manifest: dict[str, Any] = Field(default_factory=dict)


class ApplicationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    description: str | None = None
    runtime: dict[str, Any] | None = None


class ApplicationRollback(BaseModel):
    version: int = Field(ge=1)


class ApplicationBuildCreate(BaseModel):
    version: int | None = Field(default=None, ge=1)
    image: str | None = Field(default=None, max_length=500)


class ApplicationDeploymentCreate(BaseModel):
    build_id: str | None = None
    version: int | None = Field(default=None, ge=1)
    image: str | None = Field(default=None, max_length=500)
    environment: str = Field(default="production", pattern=r"^(dev|staging|production)$")
    replicas: int = Field(default=1, ge=1, le=50)
    container_port: int = Field(default=8080, ge=1, le=65535)
    health_path: str = Field(default="/healthz", max_length=200)
    env: dict[str, str] = Field(default_factory=dict)
    secret_refs: dict[str, str] = Field(default_factory=dict)


class QuotaUpdate(BaseModel):
    cpu_millicores: int = Field(default=2000, ge=100)
    memory_mb: int = Field(default=4096, ge=128)
    gpu_count: int = Field(default=0, ge=0)
    concurrent_runs: int = Field(default=10, ge=1)
    monthly_tokens: int = Field(default=1000000, ge=1000)
    enabled: bool = True


class EnabledUpdate(BaseModel):
    enabled: bool


class RoleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,78}[a-z0-9]$", max_length=80)
    description: str = ""
    permissions: list[str] = Field(default_factory=list)


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = None
    permissions: list[str] | None = None


class KnowledgeBaseAccessCreate(BaseModel):
    user_id: str
    access_level: str = Field(default="reader", pattern=r"^(reader|editor|owner)$")


class ApprovalRequest(BaseModel):
    approved: bool
    comment: str = ""


class KnowledgeBaseCreate(BaseModel):
    project_id: str
    name: str = Field(min_length=2, max_length=160)
    description: str = ""


class SkillCreate(BaseModel):
    project_id: str
    name: str = Field(min_length=2, max_length=160)
    version: str = "1.0.0"
    description: str = ""
    instructions: str = Field(min_length=1)
    manifest: dict[str, Any] = Field(default_factory=dict)


class PluginCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    kind: str = "http"
    endpoint: str = Field(min_length=8, max_length=800)
    manifest: dict[str, Any] = Field(default_factory=dict)
    secret: str = ""


class MCPServerCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    endpoint: str = Field(min_length=8, max_length=800)
    transport: str = Field(default="streamable_http", pattern=r"^(streamable_http|sse|stdio)$")
    manifest: dict[str, Any] = Field(default_factory=dict)
    secret: str = ""


class ModelTestRequest(BaseModel):
    prompt: str = "ping"
    kind: str = Field(default="health", pattern=r"^(health|chat|embedding)$")


class TenantPolicyUpdate(BaseModel):
    safety: dict[str, Any] = Field(default_factory=dict)
    pricing: dict[str, Any] = Field(default_factory=dict)


class PublicAppInvokeRequest(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)


class EvaluationCase(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    expected_contains: list[str] = Field(default_factory=list, max_length=20)


class EvaluationRequest(BaseModel):
    agent_id: str
    cases: list[EvaluationCase] = Field(min_length=1, max_length=20)


class EvaluationJobCreate(EvaluationRequest):
    priority: int = Field(default=5, ge=0, le=9)


class GpuLeaseRequest(BaseModel):
    requested_count: int = Field(default=1, ge=1, le=128)
    ttl_seconds: int = Field(default=3600, ge=60, le=86400)
    run_id: str | None = None


class SandboxRunCreate(BaseModel):
    runtime: str = Field(default="nodejs", pattern=r"^(nodejs|python|go|java)$")
    source: dict[str, Any] = Field(default_factory=dict)
    application_id: str | None = None
    timeout_seconds: int = Field(default=300, ge=10, le=3600)
    cpu_millicores: int = Field(default=500, ge=50, le=4000)
    memory_mb: int = Field(default=512, ge=64, le=8192)


class BudgetUpdate(BaseModel):
    monthly_budget: float = Field(ge=0)


class ModelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    provider_type: str
    base_url: str
    default_model: str
    enabled: bool
    created_at: datetime


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,98}[a-z0-9]$", max_length=100)
    workspace_type: str = Field(default="team", pattern=r"^(personal|team)$")
    organization_id: str | None = None
    description: str = ""


class WorkspaceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    slug: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9-]{1,98}[a-z0-9]$", max_length=100)
    description: str | None = Field(default=None, max_length=2000)


class WorkspaceMemberUpsert(BaseModel):
    user_id: str
    role: str = Field(default="viewer", pattern=r"^(owner|admin|editor|viewer)$")


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    code: str = Field(default="", max_length=80)
    parent_id: str | None = None


class AgentConfigUpdate(BaseModel):
    agent_type: str = Field(default="chat", pattern=r"^(chat|chatflow|workflow|a2a)$")
    workspace_id: str | None = None
    logo_url: str = ""
    prompt_mode: str = "normal"
    prompt_template: str = ""
    variables: list[dict[str, Any]] = Field(default_factory=list)
    memory: dict[str, Any] = Field(default_factory=dict)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    experience: dict[str, Any] = Field(default_factory=dict)
    safety: dict[str, Any] = Field(default_factory=dict)


class AgentPublishRequest(BaseModel):
    changelog: str = Field(default="", max_length=500)
    version: int | None = Field(default=None, ge=1)


class PromptTemplateCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,98}[a-z0-9]$", max_length=100)
    description: str = ""
    content: str = Field(min_length=1)
    variables: list[dict[str, Any]] = Field(default_factory=list)
    workspace_id: str | None = None


class DatabaseCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    db_type: str = Field(default="postgresql", pattern=r"^(postgresql|mysql|sqlserver|oracle)$")
    host: str = ""
    port: int = Field(default=5432, ge=1, le=65535)
    database_name: str = ""
    username: str = ""
    password: str = ""
    workspace_id: str | None = None


class DatabaseQuery(BaseModel):
    sql: str = Field(min_length=1, max_length=12000)
    parameters: dict[str, Any] = Field(default_factory=dict)
    approval_id: str | None = None


class DatabaseColumnPolicy(BaseModel):
    allowed_roles: list[str] = Field(default_factory=list)
    mask: bool = False


class DatabasePolicyUpdate(BaseModel):
    columns: dict[str, DatabaseColumnPolicy] = Field(default_factory=dict)
    require_approval: bool = False
    require_native_read_only: bool = True
    max_rows: int = Field(default=100, ge=1, le=1000)
    query_timeout_ms: int = Field(default=8000, ge=500, le=60000)


class MarketplaceCreate(BaseModel):
    resource_type: str = Field(pattern=r"^(agent|skill|plugin|model)$")
    resource_id: str
    category: str = ""
    tags: list[str] = Field(default_factory=list)


class PublishBindingCreate(BaseModel):
    resource_type: str = Field(pattern=r"^(agent|workflow|application)$")
    resource_id: str
    channel_id: str
    version: int = Field(default=1, ge=1)
    config: dict[str, Any] = Field(default_factory=dict)


class ApprovalDecision(BaseModel):
    approved: bool
    comment: str = ""


class ApprovalPolicyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    request_type: str = Field(min_length=2, max_length=80)
    resource_type: str = Field(default="", max_length=40)
    approver_roles: list[str] = Field(default_factory=lambda: ["admin", "owner"])
    conditions: dict[str, Any] = Field(default_factory=dict)
    min_approvals: int = Field(default=1, ge=1, le=20)
    allow_self_approval: bool = False
    expires_in_minutes: int = Field(default=1440, ge=5, le=43200)
    enabled: bool = True


class InterventionRuleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    match_mode: str = Field(default="keyword", pattern=r"^(keyword|regex|semantic)$")
    match_content: str = Field(min_length=1)
    scope: dict[str, Any] = Field(default_factory=dict)
    preset_reply: str = Field(min_length=1)
    priority: int = Field(default=100, ge=0, le=10000)
    enabled: bool = True


class ModelExperienceRequest(BaseModel):
    provider_id: str | None = None
    message: str = Field(min_length=1, max_length=12000)
    conversation_id: str | None = None
    knowledge_base_id: str | None = None
    attachments: list[str] = Field(default_factory=list, max_length=3)


class FavoriteRequest(BaseModel):
    resource_type: str
    resource_id: str


class KnowledgeAssetCreate(BaseModel):
    asset_type: str = Field(pattern=r"^(qa|term|graph|datasource)$")
    name: str = Field(min_length=2, max_length=160)
    description: str = ""
    content: dict[str, Any] = Field(default_factory=dict)
    status: str = Field(default="draft", pattern=r"^(draft|published|enabled|disabled)$")


class AgentFeedbackCreate(BaseModel):
    feedback: str = Field(pattern=r"^(positive|negative|neutral)$")
    detail: str = ""


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    scopes: list[str] = Field(default_factory=lambda: ["agent:invoke"])
    expires_at: datetime | None = None
