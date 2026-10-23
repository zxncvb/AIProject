import { expect, test } from "@playwright/test";

const email = process.env.E2E_ADMIN_EMAIL;
const password = process.env.E2E_ADMIN_PASSWORD;

test.beforeAll(() => {
  if (!email || !password) throw new Error("E2E_ADMIN_EMAIL 和 E2E_ADMIN_PASSWORD 必须由 CI 提供");
});

test("管理员可以登录并打开 Agent 中心", async ({ page }) => {
  const landing = await page.goto("/");
  expect(landing).not.toBeNull();
  expect(landing.headers()["x-content-type-options"]).toBe("nosniff");

  await page.getByLabel("账号").fill(email);
  await page.getByLabel("密码").fill(password);
  await Promise.all([
    page.waitForResponse((response) => response.url().endsWith("/api/auth/login") && response.ok()),
    page.getByRole("button", { name: "登录控制台" }).click(),
  ]);

  await expect(page.getByRole("heading", { name: "工作台" })).toBeVisible();
  await page.getByRole("button", { name: "Agent 中心" }).click();
  await expect(page.getByRole("heading", { name: "Agent 中心" })).toBeVisible();
  await expect(page.getByText("创建 / 测试 Agent")).toBeVisible();
});
