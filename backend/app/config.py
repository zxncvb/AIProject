from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Enterprise AI Platform"
    app_env: str = "production"
    app_secret_key: str = "change-me-in-production"
    app_encryption_key: str = ""
    database_url: str = "sqlite+aiosqlite:///./data/platform.db"
    database_admin_url: str = ""
    redis_url: str = "redis://redis:6379/0"
    jwt_expire_minutes: int = 480
    bootstrap_tenant: str = "Acme Corporation"
    bootstrap_tenant_slug: str = "acme"
    bootstrap_admin_email: str = "admin@acme.local"
    bootstrap_admin_password: str = "ChangeMe_123456"
    otel_exporter_otlp_endpoint: str = ""
    allowed_http_hosts: str = ""
    artifact_dir: str = "./data/artifacts"
    model_timeout_seconds: int = 120
    cors_origins: str = "http://localhost:13000,http://localhost:3000"
    qdrant_url: str = "http://qdrant:6333"
    qdrant_vector_size: int = 1536
    embedding_model: str = "text-embedding-3-small"
    oidc_issuer_url: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_redirect_uri: str = "http://localhost:13000/auth/oidc/callback"
    oidc_scopes: str = "openid profile email"
    oidc_auto_provision: bool = False
    oidc_email_claim: str = "email"
    oidc_groups_claim: str = "groups"
    oidc_roles_claim: str = "roles"
    oidc_default_role: str = "viewer"
    oidc_group_role_map: str = "{}"
    oidc_sync_roles: bool = False
    oidc_require_email_verified: bool = False
    oidc_allowed_domains: str = ""
    ldap_url: str = ""
    ldap_bind_dn: str = ""
    ldap_bind_password: str = ""
    ldap_user_search_base: str = ""
    ldap_user_search_filter: str = "(mail={email})"
    ldap_auto_provision: bool = False
    ldap_tls_verify: bool = True
    secret_backend: str = "fernet"
    vault_addr: str = "http://vault:8200"
    vault_token: str = ""
    vault_transit_mount: str = "transit"
    vault_transit_key: str = "enterprise-ai-platform"
    vault_namespace: str = ""
    safety_mode: str = "redact"
    safety_max_input_chars: int = 12000
    safety_block_prompt_injection: bool = False
    finops_currency: str = "CNY"
    finops_token_price_per_1k: float = 0.02
    finops_gpu_price_per_second: float = 0.0005
    finops_cpu_price_per_second: float = 0.00001
    extension_allowed_capabilities: str = "http.read,http.write,mcp.tool"
    gpu_total_count: int = 0
    gpu_lease_ttl_seconds: int = 3600
    gpu_node_names: str = ""
    sandbox_queue: str = "ai_platform:sandbox_runs"
    evaluation_queue: str = "ai_platform:evaluation_jobs"
    alert_webhook_url: str = ""
    alert_dingtalk_webhook_url: str = ""
    alert_feishu_webhook_url: str = ""
    alert_wecom_webhook_url: str = ""
    sqlserver_odbc_driver: str = "ODBC Driver 18 for SQL Server"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    @property
    def allowed_hosts(self) -> set[str]:
        return {item.strip().lower() for item in self.allowed_http_hosts.split(",") if item.strip()}

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def artifact_path(self) -> Path:
        path = Path(self.artifact_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def oidc_allowed_domain_list(self) -> set[str]:
        return {item.strip().lower() for item in self.oidc_allowed_domains.split(",") if item.strip()}

    @property
    def extension_capability_list(self) -> set[str]:
        return {item.strip() for item in self.extension_allowed_capabilities.split(",") if item.strip()}

    @property
    def gpu_node_name_list(self) -> list[str]:
        return [item.strip() for item in self.gpu_node_names.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
