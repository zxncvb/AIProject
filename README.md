# 企业级 AI 中台

这是一个可通过 Docker 部署的企业级 AI 中台，包含多租户、项目与环境、RBAC、模型与算力、智能体、工作流、知识库、技能、插件、审计、可观测与 Kubernetes 部署能力。

## 本次已实现的八项生产能力

1. PostgreSQL RLS：租户策略已启用，API/Worker 可使用独立的 `platform_runtime` 非 owner 账号运行。
2. 灰度发布：按稳定哈希进行确定性流量分配，支持生产环境灰度、手工回滚和 Prometheus 错误率自动回滚脚本。
3. CI/CD：GitHub Actions 构建并推送前后端镜像、数据库迁移、Kubernetes 发布、评测门禁和失败回滚。
4. Kubernetes：命名空间、Deployment、GPU Worker、Ingress、HPA、NetworkPolicy、Secret 示例和 Kustomize。
5. 企业登录：OIDC 单点登录和 LDAP 登录 API，并在中文前端提供登录入口。
6. 可观测：Prometheus、Alertmanager、Grafana、Loki、Promtail、Tempo、OpenTelemetry。
7. 工作流引擎：版本化 DAG、发布、灰度、Webhook、条件节点、节点重试和超时。
8. 知识库：TXT/Markdown/JSON/CSV/PDF/DOCX/XLSX 文档解析，Redis 异步索引，关键词与向量混合检索。
9. 应用中心：低代码/全代码应用资产、版本、运行时配置和发布状态。
10. 工作流高级调度：真实条件分支、循环/并行节点、间隔定时触发、租户并发配额和运行用量。
11. 安全治理：Redis API 限流、安全响应头、插件地址白名单和插件/技能启停生命周期。
12. 生产运行增强：应用运行入口、应用回滚/删除、工作流图校验、输入 Schema 校验和模型健康检测。
13. 权限与扩展治理：自定义角色权限目录、知识库成员授权、Skill 执行、插件密钥透传和 MCP 服务登记。
14. 审计与运维：审计 CSV 导出、运行失败率/用量摘要、密码变更和 CI 单元测试门禁。

## Docker 启动

```powershell
Copy-Item .env.example .env
# 生产环境请修改 APP_SECRET_KEY、APP_ENCRYPTION_KEY、BOOTSTRAP_ADMIN_PASSWORD、POSTGRES_PASSWORD 等密钥
docker compose up -d --build
```

访问地址：

- 前端：http://localhost:13000
- API 文档：http://localhost:18080/docs
- Grafana：http://localhost:13001
- Prometheus：http://localhost:19090

应用中心和算力治理 API：`/api/applications`、`/api/compute/quota`、`/api/compute/usage`。
工作流定时触发 API：`/api/workflows/{workflow_id}/schedules`。
应用运行入口：`/public/apps/{tenant_slug}/{app_slug}`；模型检测：`/api/models/{provider_id}/test`；MCP 服务：`/api/mcp-servers`。

## 本次企业能力包

- 身份：OIDC/LDAP、组到角色映射、邮箱域名限制、自动入租户。
- 模型：聊天接口、Embedding 接口、向量维度检测和 Qdrant 集合自适应。
- 应用：`POST /public/apps/{tenant_slug}/{app_slug}/invoke` 可调用绑定的已发布工作流；全代码应用需要配置受控沙箱镜像。
- 安全：`/api/safety/check`、租户安全策略、PII 脱敏、提示词注入检测。
- 评测：`POST /api/evaluations/run` 使用测试集调用智能体并返回通过率。
- FinOps：`/api/finops/summary` 提供 Token、CPU、GPU 用量和租户估算成本。
- 扩展治理：插件/MCP manifest 的 capabilities 白名单校验。
- 运维：多区域 Kustomize overlay、灾备恢复演练脚本、镜像漏洞/签名扫描脚本、Alertmanager 生产模板。

低代码应用绑定工作流时，运行时 JSON 至少包含：

```json
{
  "public": true,
  "workflow_id": "已发布工作流 ID",
  "app_key": "可选的调用密钥"
}
```

## 优先级能力（当前版本）

完整架构、代码结构、企业汇报口径和生产验收清单见：[ARCHITECTURE_AND_EXECUTIVE_GUIDE.md](E:/Codex/enterprise_ai_platform/ARCHITECTURE_AND_EXECUTIVE_GUIDE.md)。

- MFA：`/api/me/mfa/setup`、`/api/me/mfa/enable`、`/api/me/mfa/disable`；登录请求支持 `mfa_code`。
- SCIM 2.0：管理员先创建 `/api/admin/scim/tokens`，外部身份系统使用 `/scim/v2.0/{tenant}/Users` 同步用户。
- GPU：`/api/compute/gpu/leases` 提供带过期时间的租约队列；`GPU_TOTAL_COUNT` 配置平台容量。
- 全代码沙箱：`/api/runtime/sandbox/runs` 生成无特权、只读根文件系统、禁网的 Kubernetes Job，由 `app.sandbox_controller` 提交到集群。
- 异步评测：`/api/evaluations/jobs` 入队，由 worker 执行并通过查询接口读取结果。
- 插件治理：新插件默认为 `pending`，必须通过 `/api/plugins/{id}/approve` 后才允许测试和工作流调用。
- 告警适配：`/api/admin/alerts/test` 支持通用 Webhook、钉钉、飞书、企业微信；地址通过环境变量配置。
- 密钥轮换：`/api/admin/security/rotate-secrets` 重新加密模型、插件、MCP、MFA 密钥。

### 重新部署与升级

```powershell
docker compose build backend worker frontend
docker compose -f docker-compose.yml -f docker-compose.rls.yml up -d backend worker frontend
docker compose exec -T backend alembic upgrade head
Get-Content -Raw -Encoding utf8 deploy/postgres/rls.sql | docker compose exec -T postgres psql -U platform -d platform
```

Kubernetes 环境还需部署 `deploy/k8s/priority-runtime.yaml`，并把 PostgreSQL、Redis、Qdrant 换成企业运维的高可用 Operator 集群。`deploy/k8s/stateful-ha.example.yaml` 仅为 Operator 配置参考，必须在目标集群完成备份恢复、故障切换和数据一致性验收后再上线。

优先级能力验收：

```powershell
./deploy/acceptance/priority-runtime.ps1 -Password '你的管理员密码'
```

## 启用运行时 RLS

当前目录已提供 `docker-compose.rls.yml`。先确保 `.env` 中存在 `POSTGRES_RUNTIME_PASSWORD` 和 `POSTGRES_PASSWORD`，再执行：

```powershell
docker compose -f docker-compose.yml -f docker-compose.rls.yml up -d backend worker
```

首次部署或迁移环境可执行：

```powershell
Get-Content -Raw deploy/postgres/enable-rls.sql | docker compose exec -T postgres psql -U platform -d platform
Get-Content -Raw deploy/postgres/rls.sql | docker compose exec -T postgres psql -U platform -d platform
```

生产环境请把示例密码替换为随机长密码，并使用 Secret/ExternalSecret 管理，不要把真实密钥提交到代码仓库。

## 灰度发布与自动回滚

发布灰度版本：

```powershell
./deploy/ci/canary-release.ps1 -BaseUrl http://localhost:18080 -Token $token -WorkflowId $workflowId -TrafficPercent 10
```

检查错误率并在超阈值时回滚：

```powershell
./deploy/ci/auto-rollback.ps1 -BaseUrl http://localhost:18080 -Token $token -WorkflowId $workflowId -PrometheusUrl http://localhost:19090
```

## Kubernetes

生产环境需先准备真实 Secret、镜像仓库、Ingress 域名、PostgreSQL/Redis/Qdrant 地址和 GPU 节点，然后：

```powershell
kubectl apply -k deploy/k8s
```

`deploy/k8s/secrets.example.yaml` 仅为字段示例，不能直接作为生产密钥使用。

## 工作流图示例

```json
{
  "nodes": [
    {"id":"start","type":"default","data":{"kind":"input"}},
    {"id":"answer","type":"default","data":{"kind":"llm","prompt":"{{input.question}}"}},
    {"id":"end","type":"default","data":{"kind":"output","value":"{{previous.text}}"}}
  ],
  "edges": [
    {"id":"e1","source":"start","target":"answer"},
    {"id":"e2","source":"answer","target":"end"}
  ]
}
```
## 企业身份接入

中台登录支持通用 OIDC 和 LDAP，不绑定某一家云厂商。生产环境推荐使用阿里云 IDaaS（EIAM）或自建 Keycloak，通过 OIDC 接入；如果企业已经有 AD/LDAP，可让 IDaaS 或 Keycloak 作为身份代理，再由中台统一接收 OIDC 登录。

OIDC 组/角色映射可通过 `.env` 配置：

```env
OIDC_AUTO_PROVISION=true
OIDC_SYNC_ROLES=true
OIDC_GROUPS_CLAIM=groups
OIDC_ROLES_CLAIM=roles
OIDC_DEFAULT_ROLE=viewer
OIDC_GROUP_ROLE_MAP={"ai-admin":"admin","ai-developer":"developer","ai-operator":"operator"}
```

`OIDC_SYNC_ROLES=true` 会按身份系统的组或角色声明同步平台角色；自定义角色使用平台内的角色 `slug`。启用前应先在平台创建对应自定义角色，并确认身份系统只向可信用户签发这些组声明。

## 当前中文控制台功能

当前前端已经将参考界面中的主要工作区与平台管理入口接入真实 API：

- Agent 编排：提示词、变量、记忆、能力配置、版本发布、运行统计。
- 模型体验与模型广场：模型调用测试、能力目录、上下文长度和价格信息。
- 工作流与应用：可视化编排、版本、发布、运行、低代码/全代码应用资产。
- 知识与数据：知识库文档、混合检索、数据库连接登记、只读 SQL 测试入口。
- 提示词与扩展：提示词模板、Skills、插件审批、MCP 服务。
- 生产治理：发布渠道绑定、审批中心、组织/工作区、平台统计、SCIM、FinOps、审计。
- 生命周期：Agent 导入/导出/复制/删除、资源编排、触发器、反馈统计；工作流版本、图校验、生产发布、灰度记录和定时调度。
- 创建与管理：Agent 创建支持类型、工作空间、模型、知识库绑定；平台管理页已接入安全策略、身份状态、计费预算和干预规则。
- 知识扩展：问答库、术语库、图谱库、数据源资源 CRUD；数据库详情、PostgreSQL 表结构同步和只读查询结果。
- 市场与账号：市场资源详情/安装/收藏、插件/Skill/MCP Debug、个人 API Key 创建与撤销。

登录账号和密码由 `.env` 中的 `BOOTSTRAP_ADMIN_EMAIL`、`BOOTSTRAP_ADMIN_PASSWORD` 注入；仓库不保存任何登录密码或密钥。

数据库问答接口支持 PostgreSQL 只读实时查询，强制单语句、自动最多 100 行和 8 秒超时；MySQL/SQL Server 还需在企业镜像中安装对应驱动。生产环境仍需配置数据库审批、网络白名单、字段脱敏和结果权限策略。

