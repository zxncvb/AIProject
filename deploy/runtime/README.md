# 应用运行时安全契约

当前中台的低代码公开应用可以绑定已发布工作流并通过 `/public/apps/{tenant}/{slug}/invoke` 排队执行。全代码应用必须使用独立的运行时镜像，不允许后端进程直接执行租户提交的代码。

生产运行时镜像必须满足：

- 非 root 用户
- 只读根文件系统
- 无 Docker socket
- 默认无出站网络，只允许显式的工具代理
- CPU、内存、GPU、执行时间和临时磁盘限制
- 运行实例使用独立 ServiceAccount
- 使用 gVisor、Kata Containers 或等价隔离运行时
- 结束后自动删除 Pod，并将日志和 Trace ID 回传平台

运行时清单示例：

```json
{
  "runtime_class": "gvisor",
  "image": "registry.example.com/enterprise-app-runtime:2026.10",
  "cpu": "500m",
  "memory": "512Mi",
  "timeout_seconds": 120,
  "network_policy": "deny-all"
}
```

平台只保存和校验清单，不在 API 进程中执行不可信源码。需要接入实际运行时控制器后，才可把 `full_code` 应用标记为可部署。
