import { expect, test } from "@playwright/test";

const email = process.env.E2E_ADMIN_EMAIL;
const password = process.env.E2E_ADMIN_PASSWORD;

test.beforeAll(() => {
  if (!email || !password) throw new Error("E2E_ADMIN_EMAIL 和 E2E_ADMIN_PASSWORD 必须由 CI 提供");
});

async function login(page) {
  await page.goto("/");
  await page.getByLabel("账号").fill(email);
  await page.getByLabel("密码").fill(password);
  await Promise.all([
    page.waitForResponse((response) => response.url().endsWith("/api/auth/login") && response.ok()),
    page.getByRole("button", { name: "登录控制台" }).click(),
  ]);
  await expect(page.getByRole("heading", { name: "工作台" })).toBeVisible();
}

test("管理员可以登录并打开 Agent 中心", async ({ page }) => {
  const landing = await page.goto("/");
  expect(landing).not.toBeNull();
  expect(landing.headers()["x-content-type-options"]).toBe("nosniff");

  await login(page);
  await page.getByRole("button", { name: "Agent 中心" }).click();
  await expect(page.getByRole("heading", { name: "Agent 中心" })).toBeVisible();
  await expect(page.getByText("创建 / 测试 Agent")).toBeVisible();
});

test("Agent SSE 事件会显示工具轨迹和最终答案", async ({ page }) => {
  const agent = { id: "agent-stream", name: "流式回归 Agent", description: "CI", enabled: true, version: 1, provider_id: "provider-1" };
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/auth/login") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ user: { email }, access_token: "" }) });
    if (path === "/api/me") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ user: { email, display_name: "CI" }, role: "admin", tenant: { name: "CI" } }) });
    if (path === "/api/agents/agent-stream/chat/stream") {
      const body = [
        "event: token\ndata: {\"text\":\"正在查询\"}\n\n",
        "event: tool_call\ndata: {\"id\":\"call-1\",\"name\":\"lookup_order\"}\n\n",
        "event: tool_result\ndata: {\"id\":\"call-1\",\"name\":\"lookup_order\",\"status\":\"success\"}\n\n",
        "event: token\ndata: {\"text\":\"订单已找到\"}\n\n",
        "event: done\ndata: {\"conversation_id\":\"conversation-1\",\"text\":\"正在查询订单已找到\"}\n\n",
      ].join("");
      return route.fulfill({ status: 200, headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" }, body });
    }
    if (path === "/api/agents" && request.method() === "GET") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([agent]) });
    if (path === "/api/projects" && request.method() === "GET") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([{ id: "project-1" }]) });
    if (path === "/api/workspaces" && request.method() === "GET") return route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
    if (request.method() === "GET") return route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
    return route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });

  await login(page);
  await page.getByRole("button", { name: "Agent 中心" }).click();
  await page.locator(".asset-card").first().click();
  await page.getByPlaceholder("例如：公司差旅报销标准是什么？").fill("查询订单 42");
  await page.getByRole("button", { name: "发送" }).click();

  await expect(page.getByText("工具调用轨迹")).toBeVisible();
  await expect(page.getByText("lookup_order").first()).toBeVisible();
  await expect(page.getByText("订单已找到")).toBeVisible();
  await expect(page.getByText("Agent 已完成")).toBeVisible();
});
