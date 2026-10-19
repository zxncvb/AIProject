# 版本与文档修改记录

本文件从当前版本开始记录每轮可交付修改。完整的阶段演进、架构和部署说明分别见 `PROJECT_EVOLUTION_AND_DEPLOYMENT.md` 与 `ARCHITECTURE_AND_EXECUTIVE_GUIDE.md`。

## 2026-10-20：可靠性、工作空间隔离与知识库修复

### 功能修改

- 将工作流、知识索引、异步评测和沙箱任务统一迁移到 Redis Streams 消费组，支持进程崩溃后的待处理任务认领、最多 5 次队列级重试和死信流。
- 项目正式绑定工作空间；应用、Agent、工作流、运行记录和知识库按项目继承工作空间权限。
- 提示词模板和数据库连接按工作空间隔离；增加工作空间成员列表、添加/改权和移除接口，并记录审计事件。
- Docker Compose 默认通过 `platform_runtime` 非 owner 账号运行普通请求，迁移和登录/系统任务使用管理员连接；RLS 覆盖全部当前租户表。
- 修正 Kubernetes Worker、PDB、命名空间、服务别名、只读文件系统写入目录、网络策略和 CD 镜像更新目标。
- 文件上传增加 25 MB 原文件上限、100 MB 压缩展开上限、500 万字符提取上限和扩展名白名单。
- 前后端增加 CSP、可信 Host 配置和非 root Nginx；不再从前端公开代理 `/metrics`。
- 修复知识库重复创建返回 500 的问题：现在返回可读的 409；顶部新建按钮只聚焦输入框，显式输入名称后才提交；点击知识库会加载文件并显示“已打开”反馈。

### 数据库迁移

- `20261020_workflow_reliability`：运行幂等、重试来源和模型会话。
- `20261020_workspace_isolation`：项目工作空间归属以及历史资源回填。
- `20261020_rls_enforcement`：启用全部租户表的 RLS，并在运行时角色存在时授予业务权限。

### 文档修改点

- `README.md`：更新 Docker 一键迁移/RLS 启动流程、必填密钥、Kubernetes Secret 前置条件和升级命令。
- `PROJECT_EVOLUTION_AND_DEPLOYMENT.md`：追加本轮问题、解决方案、验证结果和仍需企业环境验收的边界。
- `CHANGELOG.md`：新增统一版本与文档修改记录；后续每轮交付继续在此追加。

### 验证

- 后端容器测试通过。
- 前端 Vite 生产构建通过。
- Alembic 已升级至 `20261020_rls_enforcement`。
- Docker `migrate` 与 `db-security` 一次性任务成功结束，前后端与 Worker 正常运行。
- 知识库重复创建返回 409；新知识库创建、列表刷新均通过真实 API 验证，验证数据已清理。

## 历史阶段索引

1. Docker 最小部署与健康检查。
2. 多租户、RBAC、模型、Agent、工作流和知识库骨架。
3. 中文蓝白控制台、UTF-8 与乱码治理。
4. 工作流删除、外键清理和审计保留。
5. OIDC/LDAP/SCIM、MFA、RLS、CI/CD、Kubernetes 和可观测。
6. 应用中心、全代码沙箱、异步评测、FinOps 和发布治理。
7. 模型路由/熔断、工作流幂等/重试、模型会话、数据库字段策略和本轮可靠性加固。

各阶段详细说明见 `PROJECT_EVOLUTION_AND_DEPLOYMENT.md`。
