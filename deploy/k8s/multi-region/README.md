# 多区域部署

本目录提供两个区域的 Kustomize overlay。它们只负责部署层，不会自动复制 PostgreSQL、Redis 或 Qdrant 数据。

## 部署

```powershell
kubectl kustomize --load-restrictor LoadRestrictionsNone deploy/k8s/overlays/region-a | kubectl apply -f -
kubectl kustomize --load-restrictor LoadRestrictionsNone deploy/k8s/overlays/region-b | kubectl apply -f -
```

生产环境必须额外配置：

- 多区域 PostgreSQL 主从/云数据库复制
- Redis Sentinel 或云 Redis 高可用
- Qdrant 集群或跨区域备份恢复
- 全局流量入口、健康检查和故障切换
- 两个区域独立的 Secret，不要复用数据库管理员密码
- 数据驻留、跨境和租户路由策略

区域 overlay 不是跨区域数据库复制的替代品，切换前应执行 `deploy/backup/dr-test.ps1` 验证恢复时间目标。
