# Enterprise AI Platform Python SDK

这是公开应用 API 的最小 Python 客户端，使用标准库实现，不需要额外依赖。

```python
from enterprise_ai_platform import EnterpriseAIPlatformClient

client = EnterpriseAIPlatformClient(
    "https://platform.example.com",
    app_key="your-public-app-key",
)
runtime = client.get_runtime("acme", "service-desk")
run = client.invoke("acme", "service-desk", {"question": "如何重置密码？"})
if run.get("status") == "queued":
    result = client.get_result(run["result_token"])
```

也可以使用 `client.invoke_and_wait("acme", "service-desk", {"question": "..."})` 自动等待终态。
异步工作流或全代码应用返回 `result_token` 后，调用方应按需轮询
`GET /api/v1/public/runs/{result_token}`，令牌默认 1 小时有效并可被管理员撤销。
