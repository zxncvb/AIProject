# 企业 AI 中台：建设过程、问题修复与部署手册

本文档记录本项目从最小可运行版本到当前企业级 AI 中台版本的建设过程、每一阶段解决的问题、当前架构、部署方式，以及真正投入企业生产环境时需要重点考虑的事项。

> 文档适用目录：`E:\Codex\enterprise_ai_platform`

## 一、项目目标

本项目不是单一的聊天机器人，而是面向企业内部 AI 应用交付的控制面，目标是统一管理：

- 企业租户、项目、环境和成员权限
- 模型供应商、Embedding、算力配额和调用用量
- 智能体、知识库、工作流、技能、插件和 MCP 服务
- 应用资产、版本、发布、运行和审计
- CI/CD、灰度、Kubernetes、可观测和安全治理

核心原则是：所有生产 AI 能力都应当可配置、可审计、可回滚、可观测，并且在租户之间严格隔离。

## 二、从最小版本到当前版本的演进

### 阶段 0：Docker 安装和服务启动

最初的目标是把平台通过 Docker 跑起来，解决开发机上依赖复杂、服务启动顺序不稳定的问题。

已解决的问题：

- PostgreSQL、Redis、Qdrant、后端、前端可以统一启动
- 使用 Docker Volume 保存数据库、向量和附件数据
- 前端、API 文档和监控服务有固定访问地址
- 服务具备健康检查和重启策略

当前主要入口：

- 前端：`http://localhost:13000`
- API 文档：`http://localhost:18080/docs`
- Grafana：`http://localhost:13001`
- Prometheus：`http://localhost:19090`

### 阶段 1：最小 AI 中台骨架

随后建立了 FastAPI + React + PostgreSQL 的核心业务骨架，解决“只有页面，没有真实后端能力”的问题。

已实现：

- 用户、租户、成员和项目
- 基础 RBAC
- 模型供应商管理
- 智能体创建和对话
- 工作流创建、版本、发布和运行
- 知识库、文档上传和检索
- 技能、插件、审计和运行记录

这一步之后，平台已经从静态界面变成了能够真实写入数据库、创建资源和执行任务的系统。

### 阶段 2：中文化和蓝白色界面

根据实际使用反馈，完成了中文界面重构和蓝白色视觉统一。

已处理：

- 侧边栏、表单、按钮、状态、错误信息全部中文化
- 中英文混排规则统一
- 页面标题、空状态和提示文案统一
- 蓝白色主视觉、卡片、表格和状态标签统一
- 增加 `UTF-8` 页面声明和中文响应头

### 阶段 3：乱码和编码问题修复

这一阶段主要解决界面和接口出现问号、乱码、英文残留的问题。

已解决：

- HTML 增加 `<meta charset="UTF-8">`
- Nginx 设置 `charset utf-8`
- FastAPI 默认 JSON 响应设置为 `application/json; charset=utf-8`
- 前端增加乱码兜底方法 `cleanLabel`
- 修复模型、智能体、知识库下拉列表的异常名称
- 修复应用中心数据库中历史脏数据 `??????`
- 应用名称恢复为“流程应用验证”

### 阶段 4：工作流删除和数据一致性修复

用户反馈工作流列表不能删除。排查后发现不是按钮问题，而是运行用量表对工作流运行记录存在外键依赖。

已解决：

- 删除工作流前检查活动运行
- 先删除运行用量、发布记录、运行记录和版本记录
- 再删除工作流主体
- 删除按钮加入确认提示
- 删除后自动刷新列表
- 保留审计事件，避免治理记录被误删

### 阶段 5：企业级生产能力

随后补齐了八类平台化能力：

1. PostgreSQL RLS 租户行级隔离
2. 工作流灰度发布和自动回滚
3. GitHub Actions CI/CD
4. Kubernetes、GPU Worker、HPA、Ingress、NetworkPolicy、PDB
5. OIDC 单点登录和 LDAP 登录接口
6. Prometheus、Grafana、Loki、Tempo、Alertmanager、OpenTelemetry
7. 工作流版本化、Webhook、重试、超时和审批
8. TXT、Markdown、JSON、CSV、PDF、DOCX、XLSX 文档解析和混合检索

### 阶段 6：应用中心和高级调度

进一步补齐了：

- 应用中心
- 低代码/全代码应用资产类型
- 应用版本和运行时配置
- 应用发布状态
- 工作流间隔定时触发
- 条件分支
- 循环节点
- 并行节点
- 租户并发配额
- CPU、GPU、Token 用量统计
- Redis API 限流
- 安全响应头
- 插件地址白名单
- 技能和插件启停生命周期

### 阶段 7：当前生产增强版本

当前版本在前述基础上新增：

- 应用更新、删除、回滚和运行入口
- 公共应用运行接口：`/public/apps/{tenant_slug}/{app_slug}`
- 模型供应商健康检测和模型路由
- 工作流图结构校验
- 工作流输入 Schema 校验
- 自定义角色、权限目录和成员绑定
- 知识库成员访问控制
- Skill 执行接口
- 插件密钥透传
- MCP 服务注册、启停和连通性检测
- 审计日志 CSV 导出
- 运行失败率、活动运行、Token、GPU 摘要
- 用户密码修改
- 基础 pytest 测试和 CI 测试门禁

## 三、当前系统架构

```text
浏览器
  │
  ▼
React + Vite + Nginx
  │  /api、/public 反向代理
  ▼
FastAPI 控制面
  ├── PostgreSQL：业务数据、租户、权限、审计、运行记录
  ├── Redis：队列、限流、异步索引、定时调度
  ├── Qdrant：知识库向量检索
  ├── Worker：工作流、文档索引、Skill 执行
  ├── OpenTelemetry → Tempo：链路追踪
  ├── Prometheus / Alertmanager：指标和告警
  └── Loki / Promtail / Grafana：日志和看板
```

### 后端

- FastAPI
- SQLAlchemy Async
- Alembic
- PostgreSQL 16
- Redis 7
- Qdrant
- OpenAI 兼容模型接口

### 前端

- React
- Vite
- React Flow
- Axios
- Nginx

### 生产部署

- Docker Compose：开发、测试和单机生产
- Kubernetes：多副本、GPU Worker、Ingress、HPA、PDB
- GitHub Actions：镜像构建、迁移、部署、评测和回滚

## 四、Docker 部署

### 4.1 环境要求

- Windows、Linux 或 macOS
- Docker Desktop 或 Docker Engine
- Docker Compose v2
- 至少 4 核 CPU、8 GB 内存
- 如果使用向量检索，建议至少 12 GB 内存

### 4.2 首次部署

```powershell
cd E:\Codex\enterprise_ai_platform
Copy-Item .env.example .env
```

编辑 `.env`，生产环境至少修改：

```dotenv
APP_SECRET_KEY=替换为随机长密钥
APP_ENCRYPTION_KEY=替换为Fernet密钥
POSTGRES_PASSWORD=替换为数据库密码
POSTGRES_RUNTIME_PASSWORD=替换为运行时数据库密码
GRAFANA_ADMIN_PASSWORD=替换为Grafana密码
BOOTSTRAP_ADMIN_PASSWORD=替换为管理员初始密码
```

启动：

```powershell
docker compose up -d --build
```

启动过程会自动按顺序执行：

1. `migrate` 使用 `DATABASE_ADMIN_URL` 执行 Alembic。
2. `db-security` 创建或更新 `platform_runtime`，授权业务表并应用 RLS。
3. 前两步成功后，后端和 Worker 才会启动。

检查服务：

```powershell
docker compose ps
Invoke-RestMethod http://localhost:18080/healthz
Invoke-RestMethod http://localhost:18080/readyz
```

### 4.3 当前本地登录

当前本地环境：

```text
用户名：admin
密码由部署时 `.env` 中的 `BOOTSTRAP_ADMIN_PASSWORD` 注入，仓库不保存默认密码。
```

该密码只适用于当前本地环境。生产部署必须在 `.env` 中修改，并在首次登录后再次修改密码。

### 4.4 启用 PostgreSQL RLS

RLS 用于防止同一数据库中的不同租户读取彼此数据。

首次启用时，先检查 `.env`：

```dotenv
POSTGRES_PASSWORD=数据库管理员密码
POSTGRES_RUNTIME_PASSWORD=运行时角色密码
```

基础 Compose 已默认执行运行时角色配置和租户策略。检查一次性任务：

```powershell
docker compose ps -a migrate db-security
docker compose logs migrate db-security
```

验证：

```powershell
docker compose ps backend worker
Invoke-RestMethod http://localhost:18080/readyz
```

### 4.5 常用地址

| 服务 | 地址 |
|---|---|
| 前端 | `http://localhost:13000` |
| API 文档 | `http://localhost:18080/docs` |
| Grafana | `http://localhost:13001` |
| Prometheus | `http://localhost:19090` |
| Alertmanager | `http://localhost:19093` |
| Loki | `http://localhost:13100` |
| Qdrant | `http://localhost:16333` |
| Tempo | `http://localhost:13200` |

## 五、升级和回滚

### 5.1 升级前备份

```powershell
./deploy/backup/backup.ps1
```

备份内容包括：

- PostgreSQL custom dump
- 应用附件和文档归档
- 工作流、知识库、模型配置和审计数据

### 5.2 普通升级

```powershell
docker compose up -d --build
docker compose ps -a
docker compose logs migrate db-security backend worker frontend
```

### 5.3 数据库回滚

不要直接删除数据库表。应当：

1. 停止写入流量
2. 保存当前日志和备份
3. 按迁移版本执行 Alembic downgrade
4. 必要时使用 `deploy/backup/restore.ps1`
5. 重新启动后验证 `/readyz`、登录、工作流和知识库

## 六、主要 API 能力

### 认证和安全

```text
POST /api/auth/login
POST /api/auth/oidc/start
POST /api/auth/oidc/callback
POST /api/auth/ldap/login
POST /api/me/password
GET  /api/admin/security/status
```

### 应用中心

```text
GET    /api/applications
POST   /api/applications
GET    /api/applications/{id}
PATCH  /api/applications/{id}
DELETE /api/applications/{id}
POST   /api/applications/{id}/versions
POST   /api/applications/{id}/deploy
POST   /api/applications/{id}/rollback
GET    /api/applications/{id}/runtime
GET    /public/apps/{tenant}/{slug}
```

### 模型与算力

```text
GET  /api/models
POST /api/models
POST /api/models/{id}/test
GET  /api/models/{id}/health
GET  /api/models/route
GET  /api/compute/quota
PUT  /api/compute/quota
GET  /api/compute/usage
```

### 工作流

```text
GET  /api/workflows
POST /api/workflows
POST /api/workflows/{id}/versions
POST /api/workflows/{id}/validate
POST /api/workflows/{id}/publish
POST /api/workflows/{id}/release
POST /api/workflows/{id}/rollback
POST /api/workflows/{id}/runs
POST /api/workflows/{id}/webhook
POST /api/workflows/{id}/schedules
```

### 知识库和扩展

```text
POST /api/knowledge-bases/{id}/documents
GET  /api/knowledge-bases/{id}/documents
GET  /api/knowledge-bases/{id}/search
GET  /api/knowledge-bases/{id}/access
POST /api/knowledge-bases/{id}/access
POST /api/skills/{id}/run
GET  /api/mcp-servers
POST /api/mcp-servers
POST /api/mcp-servers/{id}/test
```

## 七、Kubernetes 部署

Kubernetes 配置位于 `deploy/k8s`，包括：

- Namespace
- Backend Deployment 和 Service
- Frontend Deployment 和 Service
- GPU Worker
- HPA
- PDB
- Ingress
- NetworkPolicy
- Secret 示例

部署前需要准备：

- PostgreSQL
- Redis
- Qdrant
- 镜像仓库
- Kubernetes 集群
- GPU 节点及 NVIDIA Device Plugin
- TLS 证书和域名
- 真实 Secret

不要直接把 `deploy/k8s/secrets.example.yaml` 当作生产密钥使用。

准备真实 Secret 后：

```powershell
kubectl apply -k deploy/k8s
kubectl -n enterprise-ai get pods
kubectl -n enterprise-ai get ingress
```

如果使用 GitHub Actions，还需要配置：

- `KUBE_CONFIG_DATA`
- GitHub Container Registry 权限
- 生产环境变量
- 评测接口地址
- 评测 Token
- Prometheus 地址
- 灰度工作流 ID

## 八、CI/CD 和灰度发布

CI 文件：

- `.github/workflows/ci.yml`
- `.github/workflows/cd.yml`

CI 当前执行：

- Python 编译检查
- Docker Compose 配置检查
- pytest 单元测试
- 前端 npm 构建

CD 当前执行：

- 构建并推送后端镜像
- 构建并推送前端镜像
- 执行数据库迁移
- Kubernetes 发布
- 等待 Deployment 滚动完成
- 执行评测门禁
- 失败时触发回滚脚本

灰度发布：

```powershell
./deploy/ci/canary-release.ps1 `
  -BaseUrl http://localhost:18080 `
  -Token $token `
  -WorkflowId $workflowId `
  -TrafficPercent 10
```

## 九、企业 AI 中台必须重点考虑的事项

### 9.1 租户隔离

不能只依赖前端传入的 tenant_id。必须同时具备：

- JWT 中的租户声明
- 后端请求上下文
- PostgreSQL RLS
- 每张业务表的 tenant_id
- Worker 执行时的租户校验
- 向量库 Collection 按租户和知识库隔离

### 9.2 权限模型

建议使用 RBAC + 资源级 ACL：

- RBAC 控制功能权限
- 项目权限控制开发范围
- 知识库 ACL 控制文档访问
- 应用权限控制发布和运行
- 审计记录所有高风险写操作

不能只在前端隐藏按钮，后端必须再次校验。

### 9.3 模型治理

需要考虑：

- 模型供应商密钥加密
- 模型健康检查
- 超时和重试
- 多供应商路由
- 失败转移
- Token 配额
- 成本核算
- 敏感数据脱敏
- Prompt 和输出审计

### 9.4 算力治理

需要区分：

- CPU 配额
- 内存配额
- GPU 配额
- 并发运行数
- Token 预算
- 单个项目预算
- 单个用户预算

Kubernetes GPU Worker 只能提供调度基础，真正的 GPU 资源管理还需要结合节点标签、队列、优先级和资源回收策略。

### 9.5 工作流可靠性

生产工作流必须具备：

- 不可变版本
- 发布前校验
- 输入 Schema
- 节点超时
- 节点重试
- 幂等键
- 人工审批
- 失败恢复
- 运行取消
- Trace ID
- 版本回滚

### 9.6 知识库质量

知识库不仅是上传文件，还应考虑：

- 文档权限继承
- 文档版本
- 文档去重
- 切片策略
- Embedding 模型版本
- OCR 和图片内容
- 表格解析
- 引用来源
- 检索评测
- 删除后的向量清理

### 9.7 插件和 MCP 安全

所有外部工具调用都应具备：

- 地址白名单
- 出站网络限制
- 请求超时
- Secret 加密
- 最小权限
- 调用审计
- 版本锁定
- 沙箱隔离
- 输入输出大小限制

不能允许插件直接访问数据库、文件系统或内部网络。

### 9.8 可观测性

至少需要三类信号：

- Metrics：吞吐量、延迟、错误率、Token、GPU、队列长度
- Logs：结构化日志、租户、项目、用户、Trace ID
- Traces：API、工作流节点、模型调用、插件调用、知识检索

还需要定义 SLO，例如：

- API 可用性 99.9%
- 工作流成功率 99%
- P95 模型响应延迟
- 知识检索 P95 延迟
- 队列等待时间

### 9.9 安全与合规

生产环境建议接入：

- Vault 或云 KMS
- OIDC/LDAP/AD
- MFA
- 密钥轮换
- 备份加密
- 审计留存
- 数据脱敏
- 网络分区
- 容器漏洞扫描
- 镜像签名
- 依赖漏洞扫描

### 9.10 业务和运营

企业 AI 中台最终要回答：

- 谁在使用模型
- 使用了多少 Token 和 GPU
- 哪些应用带来业务价值
- 哪些知识库回答质量高
- 哪些工作流经常失败
- 哪些插件存在风险
- 哪些租户超出预算
- 哪些模型应该下线

如果没有成本、质量和业务指标，平台很容易变成“功能很多但无法运营”的工具集合。

## 十、当前还需要企业环境补齐的内容

代码和本地 Docker 运行链路已经完成，但以下事项需要真实企业资源：

1. OIDC 身份提供商地址、客户端 ID 和客户端密钥
2. LDAP/Active Directory 地址、绑定账号和搜索目录
3. OpenAI 兼容模型或企业私有模型地址和密钥
4. Embedding 模型
5. GPU 节点、NVIDIA Runtime 和调度策略
6. 镜像仓库和 Kubernetes 集群
7. 域名、TLS 证书和 Ingress
8. 飞书、钉钉、企业微信或短信告警渠道
9. Vault/KMS
10. 备份存储和灾备环境

这些不是代码缺失，而是需要企业基础设施和安全凭据才能完成的接入工作。

## 十一、当前验收结果

当前已验证：

- Docker Compose 服务正常运行
- RLS 模式可以启动
- 数据库迁移版本为 `20261018_production_pack`
- 管理员登录成功

## 十二、企业身份接入说明

本项目不依赖 Microsoft Entra ID、阿里云或任何单一身份厂商。后端使用通用 OIDC 接口，也保留 LDAP 登录接口。推荐的生产接入方式是：

```text
阿里云 IDaaS / Keycloak / Entra ID
              ↓ OIDC
       企业 AI 中台
              ↓
       租户与平台 RBAC
```

OIDC 配置支持邮箱声明、组声明、角色声明、自动开户、邮箱域名限制和角色同步：

```env
OIDC_AUTO_PROVISION=true
OIDC_SYNC_ROLES=true
OIDC_GROUPS_CLAIM=groups
OIDC_ROLES_CLAIM=roles
OIDC_DEFAULT_ROLE=viewer
OIDC_GROUP_ROLE_MAP={"ai-admin":"admin","ai-developer":"developer"}
OIDC_ALLOWED_DOMAINS=example.com
```

当前已实现身份组到内置角色/自定义角色的映射。仍需企业管理员在身份服务中创建 OIDC 应用、配置回调地址、签发组声明，并在真实环境中验证 MFA、账号禁用同步和审计留存。

## 十三、企业能力包新增接口

本次继续实现了以下可运行能力：

- `/api/admin/policy`：租户安全策略和计费价格策略
- `/api/safety/check`：输入安全检查与 PII 脱敏
- `/api/evaluations/run`：基于智能体的测试集评测
- `/api/finops/summary`：Token、CPU、GPU 和估算成本
- `/public/apps/{tenant_slug}/{app_slug}/invoke`：低代码应用公开调用和工作流排队
- `/api/admin/identity/status`：OIDC/LDAP 接入状态
- `/api/finops/budget`：月度预算配置，Agent/Workflow/公开应用任务创建前强制预算检查
- `/api/publish/bindings/{binding_id}/publish`：审批校验、白名单 webhook 渠道投递和发布状态落库
- `/api/databases/{database_id}/query`：四类数据库的只读查询、命名参数绑定和最多 100 行限制

部署包新增：

- `deploy/k8s/overlays/region-a` 和 `region-b`
- `deploy/k8s/multi-region/README.md`
- `deploy/backup/dr-test.ps1`
- `deploy/security/scan.ps1`
- `deploy/observability/alertmanager.production.example.yml`
- `deploy/runtime/README.md` 和 `sandbox-networkpolicy.yaml`
- `deploy/finops/pricing.example.json`
- `deploy/evaluation/safety-cases.example.json`

这些文件解决了平台代码和生产部署流程的缺口；真实云账号、GPU 节点、镜像仓库、域名、告警机器人、数据库复制和密钥仍需由企业环境提供。
- 应用中心返回中文数据
- 公共应用运行入口可访问
- 自定义角色可以创建和删除
- 工作流校验接口正常
- 审计 CSV 导出正常
- `/readyz` 返回正常
- pytest 测试通过：`3 passed`

## 十二、常用故障排查

### 后端无法启动

```powershell
docker compose logs --tail=200 backend
docker compose run --rm migrate alembic -c /app/alembic.ini current
docker compose run --rm migrate
docker compose run --rm --no-deps db-security
```

### 页面显示旧版本

```text
浏览器按 Ctrl + F5 强制刷新
```

### 中文乱码

检查：

- 页面是否包含 UTF-8 声明
- API Content-Type 是否带 charset=utf-8
- 数据库中的字段是否已经保存为问号
- Nginx 是否使用最新镜像

### RLS 报权限错误

检查：

```powershell
docker compose ps postgres backend worker
Get-Content -Raw -Encoding utf8 deploy/postgres/rls.sql |
  docker compose exec -T postgres psql -U platform -d platform
```

### 知识库索引失败

检查：

- 是否配置可用模型供应商
- 是否配置 Embedding 模型
- Qdrant 是否正常
- `docker compose logs worker`

### 本轮补强（API Key、知识库和扩展治理）

- API Key 现在只允许申请已登记的公开调用权限：`agent:invoke`、`workflow:run`；空权限、未知权限、已过期密钥都会被后端拒绝。
- Agent 和 Workflow 对外接口支持 `Authorization: Bearer eai_...` 或 `X-API-Key`，并继续执行租户、角色、预算和安全策略校验。
- 知识库上传按 SHA-256 内容指纹去重；问答、术语、图谱、数据源资产会在写入前检查必需字段和数据类型。
- Skill、插件和 MCP manifest 统一经过扩展能力白名单校验，插件仍需审批后才能运行。
- 预算超限会在 Agent、Workflow 和公开应用入口统一返回 429；平台管理页展示最近 30 天消息、Token 和平均延迟趋势，运行记录支持 JSON 导出。
- PostgreSQL 与 MySQL 已支持连接测试、schema 同步和只读查询；SQL Server/Oracle 需要在企业镜像中接入对应驱动。
- 回归结果：Docker backend/worker 构建成功，pytest `8 passed`，`/healthz` 与 `/readyz` 正常。

## 十三、结论

当前项目已经具备一个可运行的企业 AI 中台基础版本：可以部署、登录、创建企业 AI 资源、运行工作流、管理知识库、接入模型、接入插件、执行审计并进行基本的生产观测。

## 十四、优先级补齐项

当前架构图、代码目录说明、企业领导汇报口径和标准 AI 中台建设清单见：[ARCHITECTURE_AND_EXECUTIVE_GUIDE.md](E:/Codex/enterprise_ai_platform/ARCHITECTURE_AND_EXECUTIVE_GUIDE.md)。

本轮重新实现了此前未闭环的优先级能力：MFA/SCIM 身份生命周期、GPU 租约调度、全代码沙箱 Job 控制器、异步 AI 评测、插件审批隔离、Webhook 告警适配、FinOps 月度预算、密钥轮换，以及 Kubernetes 沙箱 RBAC/NetworkPolicy 和状态组件 HA 参考资源。

本轮继续补齐成本运营和观测：运行与 Agent 调用支持 `cost_center` 归属，`/api/finops/ledger` 提供成本中心汇总/明细，`/api/finops/export` 提供 CSV 导出，`/api/observability/summary` 提供近 30 天成功率、平均延迟和 P95 延迟。历史用量默认归入 `unassigned`。

### 2026-10-20：发布、运行可靠性和自动归属优化

本轮把三个此前“有后端能力但控制台未闭环”的点补齐：

1. **统一发布中心**：控制台可以选择 Agent、工作流或应用，自动读取当前有效版本后创建发布绑定；服务端对资源租户、渠道状态和版本上限进行校验。
2. **发布绑定生命周期**：草稿绑定可以删除；已发布绑定禁止直接删除并保留审计记录，避免误操作影响线上渠道。
3. **工作流取消**：新增 `POST /api/runs/{run_id}/cancel`。取消请求会落库，Worker 在每个节点开始前读取最新状态，运行中的任务不会在取消后继续推进后续节点。
4. **成本中心自动归属**：Agent、Workflow、Webhook 和定时任务在未传入成本中心时，自动归属到 `project:{project_slug}`；显式传入的成本中心仍优先保留。

验证结果：Docker Compose 重新构建成功，后端测试 `10 passed`，前端 Vite 构建成功，`/api/publish/resources` 和 `/api/runs/{run_id}/cancel` 路由已注册，健康检查返回 200。

其中 GPU 设备绑定、Kubernetes Job 实际提交、数据库/Redis/Qdrant 多副本和跨区域复制依赖企业集群。仓库已经提供接入 API、控制器、部署清单和验收入口，但必须在真实基础设施中完成容量、恢复和安全验收，不能把本地 Compose 运行状态视作生产 HA。

升级命令：

```powershell
docker compose up -d --build
docker compose ps
```

下一阶段重点不是继续堆页面，而是接入真实企业环境，并围绕安全、成本、质量、可用性和业务价值做生产验收。

## 十七、2026-10-20：可靠队列、工作空间隔离与知识库交互修复

本轮针对“代码已有但生产边界仍松散”和知识库实际使用故障进行了集中修复。

### 已解决问题

1. **异步任务可能丢失**：原有 Redis List 的 `BLPOP` 在 Worker 取出后崩溃会丢任务。现在统一使用 Redis Streams 消费组，支持 pending 任务认领、重试计数、死信流和旧队列迁移。
2. **工作空间只有展示、没有真正隔离**：项目新增 `workspace_id`，应用、Agent、工作流、运行和知识库通过项目继承权限；提示词和数据库连接按自身工作空间过滤。
3. **缺少空间成员管理**：新增成员列表、添加/更新角色、移除接口；保护唯一所有者并写入审计日志。
4. **基础 Compose 绕过 RLS**：普通业务连接改用 `platform_runtime`，管理员连接仅用于迁移、引导、登录发现和系统 Worker；Compose 自动完成迁移、角色配置和 RLS 重放。
5. **Kubernetes 清单不能完整闭环**：修正 Worker 名称/PDB、命名空间、前端到后端服务解析、运行目录、DNS 与同命名空间网络策略，以及 CD 中迁移和镜像发布目标。
6. **知识库重复创建返回 500**：后端捕获唯一约束并返回 409 与中文原因；前端会识别同名知识库并直接打开，不再重复提交。
7. **知识库列表点击缺少反馈**：点击后立即切换详情、加载文档、清理旧检索结果并显示当前打开的知识库。
8. **顶部新建按钮误提交默认名称**：改为聚焦名称输入框，只有填写名称并点击表单“新建”后才创建。
9. **文档上传资源边界不足**：增加文件类型、原始大小、压缩展开大小和提取文本字符数限制，拦截异常 Office 压缩包。
10. **浏览器与容器基线不足**：前端改用非 root Nginx，增加 CSP 等响应头，移除公网 `/metrics` 代理，并补齐 25 MB 代理上传限制。

### 本轮迁移

- `20261020_workspace_isolation`：新增项目工作空间外键，把历史项目、Agent 配置、提示词和数据库连接回填到默认工作空间。
- `20261020_rls_enforcement`：对当前全部租户表启用策略，并为已存在的 `platform_runtime` 授予业务访问权限。

### 验证结果

- Docker Compose 配置校验通过。
- Alembic 已升级至 `20261020_rls_enforcement`。
- `migrate` 和 `db-security` 均以退出码 0 完成。
- 后端测试和前端生产构建通过。
- `/healthz`、登录、项目、知识库列表均正常。
- 同名知识库创建真实返回 409；不同名知识库可创建并立即出现在列表；验证记录已删除。

### 仍需企业环境完成的验收

- 使用两个真实租户和多个工作空间进行越权/渗透测试。
- 在 Kubernetes 中验证 ExternalSecret、PostgreSQL 运行时角色、Ingress 域名、NetworkPolicy 和沙箱 RuntimeClass。
- 对 Redis Streams 执行 Worker 强杀、重复投递和积压压测，并配置死信流告警。
- 对 PDF/Office 文档接入企业病毒扫描或内容安全服务；当前实现的是格式与资源上限，不等同于恶意文件扫描。

### 本轮文档修改点

- `README.md`：改为当前真实的一键迁移与 RLS 部署方式，更新必填密钥和 Kubernetes 前置条件。
- `PROJECT_EVOLUTION_AND_DEPLOYMENT.md`：增加本节，并修正首次部署、升级和 RLS 命令。
- `CHANGELOG.md`：建立后续每轮都追加的统一修改记录。

## 十五、参考界面补齐记录（本轮）

结合 `hiagent-ui-tour/screenshots` 的 135 张界面参考图，本轮完成了中文蓝白控制台的主要产品闭环：模型体验/模型广场、Agent 编排、数据库入口、提示词模板、快速对话、探索市场、发布渠道、审批中心、平台统计、账号中心和安全中心。前端入口均已连接后端 API，不再是静态演示数据。

新增后端资源包括组织与工作区、Agent 配置/版本/事件/API Key、提示词模板、数据库连接与 schema 快照、知识扩展资源、市场资源、收藏、发布渠道与绑定、审批申请、干预规则等。Agent 已覆盖导入、导出、复制、删除、资源编排、触发器和反馈统计；数据库问答已支持 PostgreSQL、MySQL、SQL Server、Oracle 的只读实时查询与表结构同步，其中 SQL Server 需要在企业镜像中安装 Microsoft ODBC Driver。

验收结果：前端 Vite 构建通过；后端 pytest `10 passed`；数据库迁移已升级至 `20261019_finops_observability`；登录、工作区、模型目录、提示词、数据库、市场、发布绑定、审批、安全、FinOps、观测等接口均返回预期结果；Docker Compose 中前后端、Worker、PostgreSQL、Redis、Qdrant、Prometheus、Grafana 等服务正常运行。

## 十六、2026-10-20：6 条生产主线与 15 个能力检查点

本节按代码和本地验收证据记录状态，不把“有配置入口”算作在企业生产环境完成验收。

| 生产主线 | 本轮已落地 | 仍需外部环境验收 |
| --- | --- | --- |
| 身份与多租户 | 沿用 OIDC/LDAP/SCIM、角色控制；模型会话按租户和用户隔离，运行重试/取消增加归属校验 | 接入企业身份源，验证组映射、离职禁用、跨租户渗透测试 |
| 算力与沙箱 | Job 强制真实命令、非 root、只读根目录、临时存储限制、日志回收和终态清理 | 集群实际执行、RuntimeClass/gVisor/Kata、GPU 设备绑定、网络隔离实测 |
| 模型与知识 | 健康排序、暂时错误重试、回退和熔断；模型体验保存会话、文本附件、知识引用 | 真实模型负载、故障切换压测、OCR/多模态输入 |
| 应用与工作流 | 全代码批处理调用、版本部署校验；运行幂等、失败任务重试、审批等待状态修复 | 全代码 CI/镜像构建、交互式应用托管、长事务补偿及并发压测 |
| 安全与数据 | 字段级可见性/脱敏、查询审计增强；发布绑定校验实际发布版本 | 数据库原生只读角色/行级隔离、DLP 审核、渠道端到端验收 |
| 观测与运维 | 运行中心可查看详情、失败任务、取消/重试；沿用现有 Prometheus/Grafana/FinOps | 多副本 HA、跨区域恢复演练、SLO 告警闭环 |

15 个能力检查点的当前状态：

1. 模型提供商路由与健康排序：已实现；真实故障注入待验收。
2. 模型调用暂时错误重试：已实现；第三方限流策略需按供应商调优。
3. 模型回退与熔断：已实现配置型回退；需配置 `fallback_provider_ids` 并压测。
4. 模型体验会话：已实现用户隔离、列表、查看和删除。
5. 知识库引用：已实现片段检索与引用展示；需要业务知识准确率评测。
6. 文本附件：已实现受限文本输入；图片、PDF 即时解析/OCR 未实现。
7. 工作流幂等：已实现 API 键和数据库唯一约束；调用方需传 `idempotency_key`。
8. 失败任务重试：已实现新运行记录和来源关联；业务副作用补偿仍需逐节点定义。
9. 人工审批等待：已修复误标记成功；企业审批策略仍需对接。
10. 全代码沙箱：已实现更严格 Job 模板和控制器日志/清理；本地 Compose 不执行 Job。
11. 全代码应用调用：已接入沙箱批任务，公开调用必须带密钥；不是 Web 服务托管或自动镜像构建。
12. 数据库字段权限：已实现管理员策略与返回结果脱敏；不能代替数据库原生最小权限。
13. 发布版本校验：已实现对 Agent、工作流、应用当前发布版本的核验；外部渠道回调待联调。
14. 中文界面：新页面和状态已中文化；当前源码扫描无 UTF-8 替换字符，仍需在目标浏览器逐屏验收。
15. 可观测入口：运行详情、失败列表及原有指标可用；生产告警值班和恢复演练待企业执行。

本轮本地验收：数据库迁移至 `20261020_workflow_reliability`，后端 pytest `14 passed`，前端容器 Vite 构建成功，`/healthz` 与 `/readyz` 返回 200，首页响应声明 `charset=utf-8`。这些是本地功能验收，不等同于上述生产环境验收。迁移和容器升级顺序请以 README 中最新命令为准；密钥只放入环境变量或 Secret，不写入仓库。
