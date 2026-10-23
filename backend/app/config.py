from functools import lru_cache
import re
from pathlib import Path

from cryptography.fernet import Fernet
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Enterprise AI Platform"
    app_env: str = "production"
    app_secret_key: str = "change-me-in-production"
    app_encryption_key: str = ""
    database_url: str = "sqlite+aiosqlite:///./data/platform.db"
    database_admin_url: str = ""
    controller_database_url: str = ""
    redis_url: str = "redis://redis:6379/0"
    jwt_expire_minutes: int = 480
    jwt_refresh_expire_days: int = 30
    login_failure_limit: int = 5
    login_lock_minutes: int = 15
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True
    password_reset_ttl_minutes: int = 30
    frontend_base_url: str = "http://localhost:13000"
    bootstrap_tenant: str = "Acme Corporation"
    bootstrap_tenant_slug: str = "acme"
    bootstrap_admin_email: str = "admin@acme.local"
    bootstrap_admin_password: str = "ChangeMe_123456"
    otel_exporter_otlp_endpoint: str = ""
    allowed_http_hosts: str = ""
    database_allowed_hosts: str = ""
    artifact_dir: str = "./data/artifacts"
    storage_backend: str = "local"
    s3_endpoint_url: str = ""
    s3_bucket: str = ""
    s3_region: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_presign_expire_seconds: int = 900
    model_timeout_seconds: int = 120
    cors_origins: str = "http://localhost:13000,http://localhost:3000"
    trusted_hosts: str = "*"
    upload_max_bytes: int = 26214400
    upload_max_uncompressed_bytes: int = 104857600
    upload_max_archive_entries: int = 10000
    upload_allow_macros: bool = False
    upload_dlp_action: str = "report"
    knowledge_max_extracted_chars: int = 5000000
    knowledge_candidate_limit: int = 5000
    clamav_host: str = ""
    clamav_port: int = 3310
    clamav_required: bool = False
    content_scan_timeout_seconds: int = 20
    ocr_endpoint: str = ""
    ocr_api_key: str = ""
    ocr_language: str = "chi_sim+eng"
    ocr_timeout_seconds: int = 120
    ocr_min_text_chars: int = 40
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
    job_stream: str = "ai_platform:jobs"
    job_consumer_group: str = "enterprise-workers"
    worker_claim_idle_ms: int = 60000
    worker_max_attempts: int = 5
    worker_max_concurrency: int = 8
    worker_per_tenant_concurrency: int = 2
    worker_job_timeout_seconds: int = 3600
    sandbox_runtime_class: str = ""
    sandbox_ephemeral_storage_mb: int = 256
    evaluation_queue: str = "ai_platform:evaluation_jobs"
    alert_webhook_url: str = ""
    alert_dingtalk_webhook_url: str = ""
    alert_feishu_webhook_url: str = ""
    alert_wecom_webhook_url: str = ""
    sqlserver_odbc_driver: str = "ODBC Driver 18 for SQL Server"
    application_runtime_namespace: str = "enterprise-ai-apps"
    application_base_domain: str = ""
    application_registry: str = ""
    application_buildkit_image: str = "moby/buildkit:v0.20.2-rootless"
    application_runtime_class: str = ""
    sandbox_node_image: str = ""
    sandbox_python_image: str = ""
    sandbox_go_image: str = ""
    sandbox_java_image: str = ""
    publication_signing_secret: str = ""
    public_app_default_rate_limit: int = 120
    agent_tool_rate_limit_per_minute: int = 60

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    @property
    def allowed_hosts(self) -> set[str]:
        return {item.strip().lower() for item in self.allowed_http_hosts.split(",") if item.strip()}

    @property
    def database_allowed_host_list(self) -> set[str]:
        return {item.strip().lower().rstrip(".") for item in self.database_allowed_hosts.split(",") if item.strip()}

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def trusted_host_list(self) -> list[str]:
        return [item.strip() for item in self.trusted_hosts.split(",") if item.strip()] or ["*"]

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


def validate_runtime_settings(settings: Settings) -> None:
    '''Reject unsafe defaults before a production process starts.'''
    environment = settings.app_env.strip().lower()
    if environment not in {'production', 'prod'}:
        return

    errors: list[str] = []
    if not settings.app_secret_key or settings.app_secret_key == 'change-me-in-production':
        errors.append('APP_SECRET_KEY must be a unique production secret')
    if not settings.app_encryption_key:
        errors.append('APP_ENCRYPTION_KEY must be explicitly configured in production')
    else:
        try:
            Fernet(settings.app_encryption_key.encode())
        except (TypeError, ValueError):
            errors.append('APP_ENCRYPTION_KEY must be a valid Fernet key')
    if not settings.bootstrap_admin_password or settings.bootstrap_admin_password == 'ChangeMe_123456':
        errors.append('BOOTSTRAP_ADMIN_PASSWORD must be changed')
    if settings.database_url.lower().startswith('sqlite') or settings.database_admin_url.lower().startswith('sqlite'):
        errors.append('production requires PostgreSQL; SQLite is not supported')
    if settings.trusted_hosts.strip() == '*':
        errors.append('TRUSTED_HOSTS must restrict allowed hostnames')
    if settings.storage_backend.strip().lower() == 's3' and not settings.s3_bucket:
        errors.append('S3_BUCKET is required when STORAGE_BACKEND=s3')
    if settings.smtp_host and not settings.smtp_from:
        errors.append('SMTP_FROM is required when SMTP_HOST is configured')
    immutable_images = {
        'APPLICATION_BUILDKIT_IMAGE': settings.application_buildkit_image,
        'SANDBOX_NODE_IMAGE': settings.sandbox_node_image,
        'SANDBOX_PYTHON_IMAGE': settings.sandbox_python_image,
        'SANDBOX_GO_IMAGE': settings.sandbox_go_image,
        'SANDBOX_JAVA_IMAGE': settings.sandbox_java_image,
    }
    for name, image in immutable_images.items():
        digest = image.rsplit('@sha256:', 1)[-1] if '@sha256:' in image else ''
        if not re.fullmatch(r'[0-9a-fA-F]{64}', digest):
            errors.append(f'{name} must use an immutable image digest in production')
    if errors:
        raise RuntimeError('Unsafe production configuration: ' + '; '.join(errors))

@lru_cache
def get_settings() -> Settings:
    return Settings()
