# 企业级 AI 中台商用就绪度评估与整改建议

> 文档版本：v1.0  
> 评估日期：2026-10-20  
> 代码基线：`main` @ `b59cc8c`  
> 评估方式：静态代码与配置审计（只读，未修改业务代码）  
> 文档用途：产品决策、售前口径、交付验收、研发排期

---

## 摘要

**总体结论：当前版本不适合作为通用商业 SaaS 直接售卖或开放注册；建议先以“企业私有化部署项目”形态交付，并在首个付费项目前完成 P0 整改。**

当前系统已经具备较完整的企业中台骨架：多租户与 RLS、RBAC、模型网关、工作流 DAG、知识库、K8s 沙箱、审计、可观测、备份和 CI/CD 都有真实实现。但它距离“可复制的商业产品”仍有四类关键缺口：

1. **Agent 核心能力不足**：目前更接近“带知识库的聊天机器人”，缺少工具调用、Agent Loop、记忆执行和流式输出。
2. **账号生命周期不完整**：SSO 前端入口缺失，无邮件、邀请、找回密码、会话吊销和租户自助开通。
3. **对外应用运行时未闭环**：公开调用只返回异步 ID，没有结果查询；低代码应用未绑定工作流时只返回静态 JSON。
4. **商业化与质量门槛缺失**：没有计费、订阅、租户生命周期；自动化测试以单元测试为主，缺少 API/E2E 回归。

### 就绪度矩阵

| 维度 | 评级 | 结论 |
|---|---|---|
| 功能广度 | 强 | 可演示、可试点，覆盖面接近企业中台 |
| 核心 AI 能力 | 弱 | Agent 工具调用、流式、记忆缺失，构成商用阻断 |
| 多租户与权限 | 中上 | 后端隔离较扎实，前端与账号生命周期需补 |
| 安全基线 | 中 | 有安全头、限流、加密，但默认密钥和生产守卫缺失 |
| 可靠性与运维 | 中 | 有备份、监控、CI/CD，但无 PITR、日志不可结构化、部署顺序有风险 |
| 商业化能力 | 弱 | 无计费、订阅、租户开通、License |
| 工程质量 | 中下 | 单文件巨石、测试不足、缺少覆盖率门禁 |

### 三种交付形态的判断

| 交付形态 | 结论 | 说明 |
|---|---|---|
| 内部 POC / 单团队试点 | ✅ 可用 | 建议使用独立环境、固定模型、专人运维 |
| 企业私有化、单租户、K8s | ⚠️ 有条件可用 | 签约前补齐 P0；按项目制验收 |
| 多租户公有云 SaaS | ❌ 暂不可行 | 需补计费、开通、隔离验收、合规与 SLA 能力 |

---

## 0. 2026-10-23 整改复核

本文件第 1 至第 9 节保留 2026-10-20 审计基线，用于记录当时的不足和验收要求；截至 2026-10-23，代码已完成一轮 P0/P1 整改。当前状态如下：

- **已落地**：Agent 工具调用与最多三轮 Loop、同步/SSE 输出、记忆和取消用量审计；OIDC/LDAP 控制台入口、邀请/密码重置、Refresh/Logout、HttpOnly Cookie；生产启动守卫；公开应用签名结果查询、版本化 API、Python SDK 和公开表单运行页。
- **已落地**：Cron/DST、Worker 优先级与租户公平调度、RAG rerank、S3/预签名 URL、WAL/PITR 示例、结构化日志/request-id、审计哈希链、数据库连接 Host 白名单、SCIM Groups、评测 judge/回归门禁、供应商账单导入、SBOM/镜像签名、应用域名/TLS/配额/访问日志。
- **仍需真实环境验收**：Python 3.12 下 pytest 与覆盖率门禁、Docker Compose 集成测试、PostgreSQL RLS 跨租户回归、Kubernetes 控制器实际部署、PITR 恢复演练、第三方渗透测试和客户 IdP/存储兼容性。
- **仍属 P2 范围**：套餐/订阅/支付/发票/License、租户注销与数据导出、多区域容灾、完整 TypeScript/i18n/无障碍、协作和插件生态。

因此，整改后的版本可进入 CI 和企业私有化验收，但不能把“本地静态检查通过”表述为已完成真实生产验收。

### 追加复核（2026-10-23）

- 公开应用输入契约已扩展为递归 JSON Schema 子集校验，HTTP/ASGI 测试覆盖 manifest、调用、错误字段和安全响应头。
- RAG 查询已增加白名单元数据过滤，并对向量召回结果执行同一租户/文档过滤。
- 生产启动守卫新增 BuildKit 与四类沙箱运行时镜像的 sha256 digest 校验；Agent 工具调用对网络超时、429 和 5xx 增加有限退避重试。
- Agent 类型契约已收紧为实际支持的 `chat` / `chatflow`；`workflow` 和 `a2a` 从对话创建 UI 移除，并由工作流与发布通道入口承载，历史配置不会静默按聊天类型执行。
- Kubernetes Secret 示例已补齐启动守卫对应的生产必填字段，避免按交付示例部署时因默认密码、可信域名或可变镜像 tag 被拒绝启动。
- CI 冒烟已新增无模型依赖的公开应用异步闭环，实际创建并发布工作流驱动应用，调用公开 API 后轮询签名结果令牌并校验最终输出。
- CI 集成阶段已新增 runtime 角色的 PostgreSQL RLS 跨租户冒烟测试，验证两个租户上下文互不可见并自动清理测试租户。
- 灾备演练已支持指定生产备份镜像，Kubernetes CronJob 已接入 `BACKUP_S3_URI` 异地归档配置；实际 PITR 恢复仍需在客户 PostgreSQL/WAL 环境演练。
- Agent 流式调用的异常路径已补齐部分用量、失败事件和审计落库，避免模型/工具在输出中断时只返回错误而丢失计费证据。
- 公开异步应用新增 manifest 级 `callback_url`：仅允许配置的出站主机，工作流/沙箱终态发送 HMAC 签名回调并有限重试；签名结果轮询仍保留作为事实来源。
- 工作流执行已接入现有 `run_span`，OpenTelemetry 可用时生成执行 span，耗时指标按租户记录；未配置 OTel 时仍输出带 trace/tenant 的调试信息。
- 生产启动守卫已接入 API、Worker 和两个 Kubernetes 控制器：无法读取 PostgreSQL `rolsuper` 或发现业务运行账号为超级用户时 fail-fast；管理员连接仍仅供迁移/引导使用。
- 公开结果令牌查询已增加按租户/运行/客户端 IP 的 Redis 限流，并保留本地降级路径，异步结果闭环不再只有调用入口限流。
- Python SDK 已提供 URL 安全编码和 `invoke_and_wait` 异步终态等待方法，公开应用的调用、轮询和 SDK 使用路径保持一致。
- Agent 流式测试已覆盖分片工具调用重组及 `tool_call`/`tool_result`/`final` 事件链，补强了工具调用与流式输出的独立验收证据。
- PostgreSQL PITR 已从参数示例推进为可部署 Compose 覆盖配置、WAL 归档镜像、归档检查脚本和 CloudNativePG 对象存储声明；CI 新增切换 WAL 并检查 `pg_stat_archiver.archived_count` 的 smoke 测试。真实 S3/客户环境恢复演练仍未替代。
- 公开应用回调已增加持久化 outbox、租约、退避重试和 Worker 扫描；回调失败不再只依赖终态控制器进程内的短重试，轮询接口仍是最终事实来源。
- 审计哈希链新增数据库 append-only 触发器，禁止更新/删除 `audit_events`；该项仍需在真实 PostgreSQL 迁移环境验证权限行为。
- Agent 控制台已补齐 SSE 客户端闭环：消费 token、工具调用/结果、完成和错误事件，展示工具轨迹并支持取消；前端构建已通过，浏览器端到端和真实模型链路仍需 CI/客户环境验收。
- 前端 SSE 解析已抽为独立模块并加入 Node 原生回归测试，CI 在构建前执行前端测试；完整浏览器 E2E、后端覆盖率提升和真实环境验收仍未完成。

---

## 1. 评估范围与方法

本次评估覆盖：

- 后端：`backend/app/main.py`、`deps.py`、`security.py`、`config.py`、`models.py`、`services/*`、`worker.py`、控制器。
- 前端：`frontend/src/main.jsx`、`product_pages.jsx`、`extended_pages.jsx`、`main.legacy.jsx`、构建与 Nginx 配置。
- 部署：`docker-compose.yml`、`deploy/k8s/*`、`deploy/postgres/rls.sql`、`deploy/backup/*`、CI/CD 工作流。
- 文档：`README.md` 中对外宣称的能力与实际实现的对应关系。

评估方法为静态审计：逐项核对路由、服务、模型、配置、部署清单和测试。未执行渗透测试、未进行真实集群压测、未做客户环境验收。

---

## 2. 现有能力盘点

| 模块 | 已具备能力 | 成熟度 | 说明 |
|---|---|---|---|
| 身份与权限 | JWT、API Key、RBAC、自定义角色、MFA、OIDC/LDAP/SCIM 后端 | 可用需加固 | 前端无 SSO 入口；无邮件与账号生命周期 |
| 租户隔离 | Membership、项目/工作区隔离、PostgreSQL RLS、审计事件 | 可用 | 需补跨租户验收与 `users` 全局身份治理 |
| 模型网关 | OpenAI 兼容聊天/Embedding、重试、健康排序、熔断、回退 | 可用 | 无流式、无工具调用、无原生多厂商适配 |
| Agent | 提示词模板、会话持久化、RAG、模板变量 | 不完整 | 执行链路仅一次 LLM 调用 |
| 工作流 | 版本化 DAG、发布/灰度、条件/循环/并行/审批、重试/超时/补偿、取消、幂等、定时 | 可交付 | 定时仅间隔触发，无 Cron/时区 |
| 知识库 | 多格式解析、OCR、ClamAV、DLP、异步索引、Qdrant 检索 | 可用需加固 | 检索为 5000 chunk 扫描 + 简单合并，无 rerank |
| 应用中心 | 低代码资产、全代码 BuildKit 构建、K8s Deployment 托管、公开调用 | 不完整 | 低代码无真实运行时；公开调用无结果闭环 |
| 沙箱 | 非 root、只读根文件系统、Drop ALL、禁 SA token、资源限制 | 可交付（K8s） | 运行时镜像未固定 digest；控制器不在 Compose |
| 可观测 | Prometheus、Grafana、Loki、Tempo、OTel、Alertmanager | 可用需加固 | 日志非 JSON；`run_span` 未使用；无 request-id |
| 备份容灾 | pg_dump + 附件归档、SHA-256、加密、S3、DR 演练脚本 | 可用需加固 | 无 WAL/PITR，RPO 最坏 24 小时 |
| CI/CD | 编译、单测、Compose 冒烟、k6、Trivy、gitleaks、K8s 发布 | 可用需加固 | 测试深度不足；CD 迁移顺序有风险 |
| FinOps | Token/CPU/GPU 估算成本、预算拦截、台账、CSV | 可用（内部） | 不是客户账单，无真实供应商账单对账 |
| 商业化 | — | 缺失 | 无套餐、支付、发票、订阅、License、租户开通 |

---

## 3. P0 商用阻断项

以下六项建议在首个付费项目签约或上线前完成。每项均给出当前实现、商业影响、代码证据、整改建议和验收标准。

### P0-1 Agent 执行能力与产品定位不符

**当前实现**

- `chat_agent`（`backend/app/main.py:1896`）只调用一次 `call_routed_chat`（`backend/app/main.py:1927`），传入系统提示词和最近 20 条会话消息。
- 没有 Function Calling / Tool Calling，没有多步 Agent Loop，没有工具结果回填。
- Skill、Plugin、MCP 目前只有登记、测试、审批接口，**Agent 对话不会执行它们**。
- `prompt_template` 会覆盖系统提示词；`memory`、`capabilities`、`experience` 等配置基本不参与执行。
- Agent 类型（chat/chatflow/workflow/a2a）只是标签，没有对应运行时。
- 全仓库没有 SSE、`StreamingResponse` 或 WebSocket 流式输出。

**商业影响**

- 无法支撑“智能体平台”的核心卖点，与“聊天机器人 + RAG”差异不大。
- 无流式输出，首字延迟和交互体验达不到当前企业客户预期。
- 技能、插件、MCP 的治理能力无法转化为实际生产力。

**整改建议**

1. 在模型网关增加 OpenAI 兼容的 `tools` / `tool_calls` 解析和多轮工具循环。
2. 将 Skill、Plugin、MCP 注册信息转换为可调用工具，带 capability 白名单、超时、重试、限流和逐次审计。
3. 增加 `POST /api/agents/{id}/chat/stream` SSE 接口，支持取消、用量统计和错误事件。
4. 实现短期会话记忆 + 长期记忆（租户隔离、可删除、可配置保留期）。
5. 明确 Agent 类型语义：要么实现 chatflow/workflow/a2a，要么从 UI 和文档中移除。

**验收标准**

- 一个 Agent 能在 3 轮内完成“检索知识库 → 调用 MCP 工具 → 输出答案”，每一步有审计记录。
- 流式接口可正常输出、可中途取消、断线不影响计费与落库。
- 跨租户的工具、记忆、会话均不可见。
- 工具调用失败时有明确的降级或人工介入路径。

---

### P0-2 身份与账号生命周期不完整

**当前实现**

- `frontend/src/main.jsx` 只有邮箱密码 + MFA 登录，**没有任何 OIDC/LDAP 入口**；OIDC 回调逻辑只存在于未被引用的 `frontend/src/main.legacy.jsx`。
- 后端只有四个认证入口：`/api/auth/login`、`/api/auth/oidc/start`、`/api/auth/ldap/login`、`/api/auth/oidc/callback`。
- 没有忘记密码、重置密码、邮件验证、成员邀请；整个后端没有 SMTP/邮件服务。
- 没有 refresh token、没有主动吊销机制；JWT 有效期 480 分钟（`backend/app/config.py:15`），改密后旧 token 仍有效至过期。
- 登录限流仅按客户端 IP（20 次/分钟），Redis 异常时直接放行；没有账号级锁定，没有登录成功/失败审计。
- 没有租户创建/开通 API；`/api/tenants` 只能列出当前成员关系。
- SCIM 删除用户会把全局 `User.is_active` 置为 false（`backend/app/main.py:1051`），跨租户生效；没有 SCIM Groups。

**商业影响**

- 企业客户无法通过自己的 IdP 完成登录，只能在后台手工调 API。
- 员工离职、改密、权限变更无法及时使会话失效，存在安全风险。
- 没有邀请和找回密码，无法支撑规模化用户运营。
- 没有租户开通能力，SaaS 自助注册模式不成立。

**整改建议**

1. 恢复或实现 SSO 登录页与 `/auth/oidc/callback` 路由，支持 OIDC 与 LDAP 两种入口。
2. 引入 SMTP/邮件服务；实现一次性、短时效、哈希存储的重置密码和邀请 token。
3. 增加 refresh token 轮换或 `token_version`；改密、停用、角色变更时吊销旧会话。
4. 增加账号级失败计数与锁定；登录成功/失败写入审计。
5. 增加租户开通 API 和初始化流程；SCIM 删除改为停用当前租户的 membership，而不是全局用户。
6. 支持 SCIM Groups，或在文档中明确仅同步用户。

**验收标准**

- 新员工从邀请 → 设置密码 → 登录 → 加入租户全流程可完成。
- 改密后旧 token 在约定时间内失效。
- IdP 停用用户后，平台访问立即被拒绝。
- SCIM 删除只影响当前租户，不影响该用户在其他租户的身份。
- 登录失败达到阈值后账号被临时锁定，并产生审计事件。

---

### P0-3 生产安全默认值与启动守卫缺失

**当前实现**

- `backend/app/config.py:9-19` 的默认值：
  - `APP_ENV` 默认 `production`
  - `APP_SECRET_KEY` 默认 `change-me-in-production`
  - `BOOTSTRAP_ADMIN_PASSWORD` 默认 `ChangeMe_123456`
  - 未配置数据库时默认 SQLite
- 没有启动时的 fail-fast 校验，缺少 `.env` 也能以生产模式启动。
- FastAPI 默认开启 `/docs`、`/openapi.json`、`/redoc`（`backend/app/main.py:474` 未关闭）。
- API 启动时执行 `bootstrap()` 和 `Base.metadata.create_all`（`backend/app/main.py:374-377`），多副本存在 DDL/种子数据竞态，新增表可能绕过 Alembic 和 RLS 脚本。
- 前端 JWT 存放在 `localStorage`，增加 XSS 后的令牌泄露风险。

**商业影响**

- 误部署即使用公开默认密钥，属于可直接利用的高危漏洞。
- OpenAPI 暴露内部接口和数据模型，增加攻击面。
- 多副本首次启动可能因唯一约束冲突崩溃，或创建未受 RLS 保护的新表。
- 等保、渗透测试和客户安全评审难以通过。

**整改建议**

1. 增加启动守卫：生产环境下密钥为空、等于默认值、或仍使用 bootstrap 默认密码时拒绝启动，并输出明确修复指引。
2. 生产环境强制 PostgreSQL，禁止 SQLite；校验数据库账号不是超级用户。
3. 首次登录强制修改 bootstrap 密码，或只在一次性初始化 Job 中使用 bootstrap 凭据。
4. 生产环境关闭 `/docs`、`/openapi.json`、`/redoc`，或加管理员鉴权。
5. Token 改为 HttpOnly + Secure + SameSite Cookie + BFF/CSRF；至少实现短期 access token + refresh token。
6. 移除 API 启动时的 `create_all`，改为 Alembic 迁移 + 幂等 seed Job。
7. 限流增加租户、API Key、用户维度；认证接口在 Redis 故障时 fail-closed 或降级到本地限流。

**验收标准**

- 使用默认 `.env` 启动生产模式直接失败，错误信息可操作。
- 未认证访问 `/docs`、`/openapi.json` 返回 404 或 401。
- 空库、多副本滚动发布无需人工建表，且新表全部经过 Alembic 与 RLS 脚本。
- 安全评审中默认凭据、开放文档、令牌存储三项不再列为高危。

---

### P0-4 对外应用运行时未闭环

**当前实现**

- 只有两个公开路由：`GET /public/apps/{tenant}/{app}` 和 `POST /public/apps/{tenant}/{app}/invoke`（`backend/app/main.py:1483`、`:1496`）。
- 全代码应用调用返回 `sandbox_run_id`，绑定的工作流返回 `run_id`，但**没有匿名结果查询、轮询或回调接口**。
- 低代码应用未绑定工作流时，`invoke` 直接返回 `manifest.response` 静态 JSON，不是真实应用运行时。
- 全代码构建/托管依赖 `sandbox-controller`、`application-controller`，这两个服务不在 `docker-compose.yml` 中，只有 K8s 才能运行。
- 没有应用域名、证书、访问日志和按应用配额管理，只有全局 `APPLICATION_BASE_DOMAIN`。

**商业影响**

- 客户无法把“应用”真正发布给最终用户，公开 API 也无法拿到最终结果。
- “低代码发布”在售前演示中容易被理解为完整应用托管，实际能力不符，存在验收争议。
- 非 K8s 客户无法使用全代码应用能力。

**整改建议**

1. 增加签名结果令牌和 `GET /public/runs/{token}` 轮询接口，或 HMAC 签名的 Webhook 回调；令牌短时效、可撤销、绑定应用与租户。
2. 定义低代码运行时协议（页面/组件/动作/数据绑定），或明确改名为“工作流表单应用”，不要宣称完整低代码平台。
3. 将 sandbox/application controller 纳入 Compose 开发拓扑，或在 README 和售前材料中明确“仅 K8s”。
4. 增加应用域名、证书、访问日志、限流配额和调用统计。
5. 对外 API 增加版本前缀、弃用策略、OpenAPI 文档和 SDK。

**验收标准**

- 匿名调用 → 轮询或回调 → 拿到结果，全流程可演示、可压测。
- 低代码应用可渲染表单、校验输入并触发工作流。
- 每个应用可配置独立域名、调用配额和访问日志。
- 非 K8s 环境明确不支持全代码托管，且产品界面不误导用户。

---

### P0-5 测试体系与质量门禁不足

**当前实现**

- `backend/tests/` 共 22 个单元测试（`test_core.py` 5 个、`test_enterprise_completion.py` 6 个、`test_reliability.py` 6 个、`test_security_guards.py` 5 个）。
- 没有 API 集成测试、没有前端测试、没有 E2E、没有覆盖率门禁。
- CI 有 Compose 冒烟测试和 k6 负载测试，但覆盖不到权限边界、跨租户 RLS、审批流、公开应用、文件上传等高风险路径。

**商业影响**

- 权限、租户隔离、审批、公开接口等关键路径缺少回归保护。
- 无法支撑 SLA、快速迭代和多人协作开发。
- 客户安全评审和渗透测试前，内部无法先发现明显问题。

**整改建议**

1. 使用 testcontainers 或 Compose 建立 API 集成测试，覆盖登录、RBAC、跨租户 RLS、工作流、审批、上传、公开应用。
2. 使用 Playwright 建立前端 E2E：登录、Agent 对话、工作流编排、应用发布。
3. 设置覆盖率门禁（核心模块 ≥70%，整体 ≥60%），并纳入 CI。
4. 增加安全测试：越权矩阵、限流、SSRF、文件上传、JWT 篡改、默认密钥检查。
5. 保留 k6 基线，增加长工作流、并发租户、公开应用调用等场景。

**验收标准**

- PR 必须通过单元测试 + 集成测试 + E2E + 覆盖率门禁。
- 跨租户访问测试全部被拒绝，且有自动化用例。
- 关键 API 有 P95 延迟和错误率基线，发布可对比。
- 安全回归用例覆盖 OWASP API Top 10 的主要项。

---

### P0-6 工程结构与部署可靠性

**当前实现**

- `backend/app/main.py` 约 4100 行，约 150 个路由集中在一个模块。
- `cd.yml` 先 `kubectl apply -k deploy/k8s`，再执行迁移 Job 和滚动更新；全新集群首次部署时，应用可能先于 schema 启动。
- 日志为文本格式，没有 request-id、租户、用户、路由等结构化字段；`run_span` 已定义但未被使用。
- 沙箱运行时镜像多为未固定 tag（如 `node:22-bookworm-slim`），供应链可重复性不足。
- 前端是单文件 JSX，无 TypeScript、无 Router、无测试。

**商业影响**

- 故障定位慢，发布风险高，回滚依赖人工经验。
- 多团队协作成本高，功能扩展容易互相影响。
- 首次部署和灾备恢复难以标准化，不利于复制交付。

**整改建议**

1. 按领域拆分 router/service：auth、agents、workflows、knowledge、applications、admin、public。
2. CD 改为“迁移 → 验证 → 滚动发布”，使用 Helm 或 Kustomize overlay，镜像固定到 digest。
3. 日志改为 JSON，注入 request_id、tenant_id、user_id、route、latency；接入 Sentry 或 OTel error。
4. 修复或删除 `run_span`，补齐模型调用、工具调用、工作流节点的关键 span。
5. 固定沙箱基础镜像 digest，生成 SBOM，CI 增加镜像签名和漏洞门禁。
6. 增加启动探针、就绪探针、优雅停机和发布后自动验证。

**验收标准**

- 空库首次部署可由一条流水线完成，无需手工步骤。
- 任一次发布可一键回滚，回滚后健康检查通过。
- 每个请求可通过 request_id 串联日志与 trace。
- 沙箱镜像可复现构建，SBOM 和签名可审计。

---

## 4. P1 功能缺口（影响企业交付验收）

| 模块 | 缺口 | 建议 | 优先级 |
|---|---|---|---|
| 调度 | 只有间隔触发（最小 10s），无 Cron、时区、DST、错过补偿 | 增加 Cron 表达式、时区、misfire 策略和手动补跑 | P1 |
| Worker | 单循环顺序消费，长工作流阻塞同 worker 其他任务；无租户公平调度 | 增加优先级队列、租户配额、并发度配置和长任务隔离 | P1 |
| RAG | `search_chunks` 最多扫描 5000 个 chunk（`backend/app/services/knowledge.py:18`），关键词计数 + 向量结果直接合并，无 rerank | 增加分页/倒排索引、分数归一化、rerank、增量同步和元数据过滤 | P1 |
| 存储 | 附件只支持本地卷/RWX PVC，无 S3/对象存储驱动 | 增加 S3 兼容存储驱动、预签名 URL 和生命周期策略 | P1 |
| 备份 | 每日 `pg_dump`，无 WAL/PITR，RPO 最坏 24 小时 | 开启 WAL 归档/PITR，定期恢复演练并记录 RPO/RTO | P1 |
| 可观测 | 文本日志、无 request-id、无错误聚合；运行耗时指标不可用 | JSON 日志、request-id、Sentry/OTel、SLO 仪表盘和告警分级 | P1 |
| 审计 | 审计日志非防篡改，无 WORM/哈希链；登录失败未审计 | 增加哈希链或 WORM 存储、登录事件、导出审批 | P1 |
| 数据库连接器 | 管理员可配置任意 host/port，存在内网 SSRF 风险 | 增加 host 白名单、网络策略、连接审批和出站代理 | P1 |
| 供应链 | 沙箱镜像未固定 digest；CI 无 SBOM/签名门禁 | 固定 digest、生成 SBOM、镜像签名、漏洞门禁 | P1 |
| 公开 API | 无结果轮询/回调、无版本化、无 SDK | 增加结果令牌/回调、`/v1` 版本、OpenAPI 与 SDK | P1 |
| 应用中心 | 全代码仅 K8s；无域名/证书/访问日志 | Compose 开发拓扑、域名证书管理、访问日志与配额 | P1 |
| SCIM | 无 Groups；删除用户跨租户生效 | 增加 Groups 或明确文档；改为租户内 membership 停用 | P1 |
| 评测 | 只有基础通过率，无 LLM-as-judge、回归集和门禁 | 增加评测集版本、评分器、回归门禁和报告 | P1 |
| FinOps | 仅估算成本，无供应商账单对账 | 导入模型供应商账单、按租户/项目对账 | P1 |

---

## 5. P2 功能缺口（产品化与规模化）

| 模块 | 缺口 | 说明 |
|---|---|---|
| 计费与订阅 | 无套餐、订阅、支付、发票、License/Entitlement | 公有云 SaaS 的必备能力；私有化项目可暂缓 |
| 租户生命周期 | 无开通、注销、数据导出、数据保留、个人信息删除 | 影响 SaaS 合规与客户退出 |
| 合规 | 无等保、生成式 AI 服务/算法备案、数据出境、DPA 模板 | 中国区商用的前置条件，非代码问题但需列入交付计划 |
| 前端工程 | 无 TypeScript、Router、i18n、无障碍；Token 在 localStorage | 影响可维护性、国际化与安全 |
| 协作 | 无评论、@提醒、变更对比、回收站 | 影响多人协作体验 |
| 生态 | 无公开 SDK、Webhook、插件市场真实安装/计费 | 影响生态扩展 |
| 多区域 | 无 active-active、跨区容灾编排 | 依赖外部数据库/缓存/向量库 Operator |
| 数据治理 | 无数据分级分类、驻留策略、生命周期自动化 | 大型企业采购常见要求 |

---

## 6. README 对外口径修正建议

README 中有三处表述高于当前实现，建议在售前材料和验收文档中修正：

| README 表述 | 当前实现 | 建议口径 |
|---|---|---|
| “OIDC 单点登录和 LDAP 登录 API，并在中文前端提供登录入口”（第 11 行） | 后端 API 存在；`frontend/src/main.jsx` 无 OIDC/LDAP 入口 | “提供 OIDC/LDAP 后端接入能力，控制台登录入口待补齐” |
| “低代码发布”（第 15 行） | 未绑定工作流时返回静态 `manifest.response`，无页面运行时 | “支持工作流驱动的应用发布；完整低代码运行时待补齐” |
| “混合检索”（第 14 行） | 关键词计数 + 向量结果合并，无 rerank/分数归一化 | “关键词 + 向量混合召回，rerank 与大规模索引待补齐” |

此外，第 17 行“Redis API 限流”实际为**按客户端 IP 的路径级限流**，Redis 故障时放行；建议补充边界说明。

**建议做法**：在 README 增加“能力边界与适用场景”章节，明确“已实现 / 部分实现 / 规划中”，避免售前承诺与交付验收不一致。

---

## 7. 推荐商用路径

### 7.1 定位建议

**近期最现实的定位是“企业私有化 AI 中台（项目制交付）”，而不是“开箱即用的 SaaS”。**

- 单租户或少量租户，客户提供 K8s、PostgreSQL/Redis/Qdrant、IdP 和模型。
- 按项目合同验收，按年收取 License + 运维支持费用。
- 不承诺自助注册、在线支付、按量计费和 99.9% SLA。
- 每个客户独立部署，避免共享多租户 SaaS 的计费、隔离和合规复杂度。

### 7.2 三阶段路线

**阶段一：首个付费项目前（补齐 P0）**

- Agent 工具调用 + 流式输出 + 记忆。
- SSO 前端入口、密码重置/邀请、会话吊销、登录审计。
- 生产默认密钥守卫、关闭生产文档、移除启动 `create_all`。
- 公开应用结果轮询/回调，明确低代码能力边界。
- API 集成测试 + 跨租户 RLS 测试 + 覆盖率门禁。
- PITR/恢复演练、CD 迁移顺序修正、JSON 日志与 request-id。

**阶段二：可复制交付（补齐 P1）**

- Cron 调度、Worker 公平队列、RAG rerank、S3 存储。
- 应用域名/证书、访问日志、公开 API 版本化与 SDK。
- Helm/Kustomize 交付包、SBOM/镜像签名、标准化验收脚本。
- 售前材料与 README 口径统一。

**阶段三：SaaS 化（补齐 P2）**

- 租户开通/注销/数据导出、套餐与配额、订阅计费、发票。
- 多区域与高可用、合规备案、DPA、SLA 与状态页。
- 前端 TypeScript/Router/i18n、协作与生态能力。

### 7.3 售前可承诺与不可承诺

**可以承诺**

- 企业私有化部署，数据留在客户环境。
- 多租户数据隔离、RBAC、审计、审批。
- 版本化工作流 DAG、灰度、回滚、补偿。
- K8s 沙箱隔离和全代码应用托管（K8s 环境）。
- 知识库多格式解析、OCR、DLP、向量检索。
- 模型网关的 OpenAI 兼容接入、重试、熔断、回退。
- OIDC/LDAP/SCIM 后端接入能力。
- 备份/恢复脚本、监控指标和告警模板。

**不要承诺（除非先完成对应 P0/P1）**

- 开箱即用的 SSO 登录页。
- 流式对话、工具调用、多步 Agent。
- 公开应用的异步结果查询/回调。
- Cron 定时调度和时区支持。
- RPO < 1 小时的数据库容灾。
- 公有云自助注册、在线支付、按量计费。
- 多租户共享 SaaS 的 99.9% SLA。

### 7.4 合同与验收建议

1. 在合同中列明**能力边界和排除项**，特别是 SSO UI、流式、工具调用、低代码运行时、SaaS 计费。
2. SLA 与客户基础设施绑定，明确模型供应商可用性不在平台 SLA 内。
3. 验收标准使用本文第 8 节的清单，避免“功能存在”与“功能可用”的争议。
4. 将 P1 项作为后续变更单或二期范围，不纳入首期固定总价。
5. 明确数据保密、数据留存、备份责任和退出时的数据导出方式。
6. 中国区商用需同步评估等保、生成式 AI 服务/算法备案、数据出境和个人信息保护要求。

---

## 8. 交付前验收清单

### 安全与身份

- [ ] 生产环境使用默认密钥时拒绝启动。
- [ ] 生产环境关闭 `/docs`、`/openapi.json`、`/redoc`。
- [ ] OIDC/LDAP 登录页与回调全流程可用。
- [ ] 邀请、重置密码、邮件验证可用。
- [ ] 改密/停用/角色变更后旧会话失效。
- [ ] 登录失败锁定与审计事件可用。
- [ ] 租户内 SCIM 删除不影响其他租户。
- [ ] 跨租户 RLS 渗透测试全部拒绝。
- [ ] API Key scope、限流、撤销、过期全部验证。

### AI 与工作流

- [ ] Agent 可调用至少一个 MCP 工具，并有审计。
- [ ] 流式对话可输出、可取消、可计费。
- [ ] 长期记忆按租户隔离且可删除。
- [ ] 工作流条件/循环/并行/审批/补偿全路径通过。
- [ ] 工作流取消、重试、幂等、死信恢复通过。
- [ ] 定时任务符合客户时区要求（若承诺 Cron）。

### 应用与公开 API

- [ ] 公开应用调用 → 结果轮询/回调闭环。
- [ ] 低代码应用可渲染表单并触发工作流。
- [ ] 全代码应用构建、部署、回滚、下线通过（K8s）。
- [ ] 应用域名、证书、访问日志、配额可用。
- [ ] 公开 API 版本化、错误码、限流和文档齐全。

### 可靠性与运维

- [ ] 空库首次部署一条流水线完成。
- [ ] 迁移在应用滚动更新前完成。
- [ ] 数据库 PITR 与恢复演练通过，记录 RPO/RTO。
- [ ] 备份可恢复到隔离环境，SHA-256 校验通过。
- [ ] JSON 日志、request-id、trace 可串联。
- [ ] Prometheus 告警、Grafana 仪表盘、值班流程就绪。
- [ ] 关键接口压测达到客户并发预期。

### 质量与交付物

- [ ] 单元测试 + API 集成测试 + E2E 全部通过。
- [ ] 覆盖率门禁生效。
- [ ] 安全扫描（Trivy/gitleaks/CodeQL）无高危未处置项。
- [ ] SBOM 与镜像签名可审计。
- [ ] README、部署手册、运维手册、验收脚本与实现一致。
- [ ] 第三方渗透测试报告完成，高危问题闭环。

---

## 9. 评估局限

1. 本次为**静态审计**，未在真实客户环境执行全量功能、性能、容灾和渗透测试。
2. 本地默认 Python 3.14 环境未安装 `pytest`，未能执行测试；CI 已配置在 Python 3.12 下运行 22 个单元测试、Compose 冒烟测试和 k6 负载测试。
3. 代码行号基于 `main` @ `b59cc8c`，后续提交可能发生偏移。
4. 文中“商业影响”“整改建议”属于工程与产品判断，需结合目标客户、合同范围和团队资源进一步确认。
5. 未对客户模型供应商、K8s 发行版、存储类和 IdP 的兼容性做实测。

---

## 附录 A：证据索引

| 结论 | 证据位置 |
|---|---|
| Agent 只做一次 LLM 调用 | `backend/app/main.py:1896`、`:1927` |
| 无流式输出 | 全仓库无 `StreamingResponse` / `text/event-stream` / WebSocket |
| 前端无 OIDC/LDAP 入口 | `frontend/src/main.jsx` 中 OIDC/LDAP 引用为 0；`main.legacy.jsx` 才有 |
| 认证入口仅四个 | `backend/app/main.py:580`、`:605`、`:622`、`:655` |
| JWT 480 分钟、无 refresh | `backend/app/config.py:15`、`backend/app/security.py:26` |
| 默认密钥 | `backend/app/config.py:9-19` |
| 启动建表 | `backend/app/main.py:374-377` |
| 公开应用仅两个路由 | `backend/app/main.py:1483`、`:1496` |
| 低代码静态响应 | `invoke_public_application` 中 `manifest.get("response", {})` |
| SCIM 全局停用 | `backend/app/main.py:1051` |
| RAG 扫描 5000 chunk | `backend/app/services/knowledge.py:18` |
| 调度仅间隔触发 | `backend/app/services/workflow.py:297-311` |
| Worker 顺序消费 | `backend/app/services/workflow.py:590-614` |
| 限流按 IP、Redis 故障放行 | `backend/app/main.py:480-501` |
| FastAPI 文档默认开启 | `backend/app/main.py:474` |
| 控制器不在 Compose | `docker-compose.yml` 无 `sandbox-controller` / `application-controller` |
| CD 先 apply 后迁移 | `.github/workflows/cd.yml:56-60` |
| 测试仅 22 个单元测试 | `backend/tests/*.py` |
