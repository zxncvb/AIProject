import http from "k6/http";
import { check, sleep } from "k6";

const baseUrl = __ENV.PLATFORM_BASE_URL || "http://127.0.0.1:18080";
export const options = {
  scenarios: { api: { executor: "constant-vus", vus: 10, duration: "30s" } },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<1000"],
    checks: ["rate>0.99"],
  },
};

export function setup() {
  const response = http.post(`${baseUrl}/api/auth/login`, JSON.stringify({ email: __ENV.PLATFORM_ADMIN_USER, password: __ENV.PLATFORM_ADMIN_PASSWORD }), { headers: { "Content-Type": "application/json" } });
  check(response, { "登录成功": (value) => value.status === 200 && Boolean(value.json("access_token")) });
  return { token: response.json("access_token") };
}

export default function (data) {
  const headers = { Authorization: `Bearer ${data.token}` };
  const ready = http.get(`${baseUrl}/readyz`);
  const profile = http.get(`${baseUrl}/api/me`, { headers });
  const runs = http.get(`${baseUrl}/api/runs`, { headers });
  check(ready, { "就绪接口可用": (value) => value.status === 200 });
  check(profile, { "身份接口可用": (value) => value.status === 200 });
  check(runs, { "运行列表可用": (value) => value.status === 200 });
  sleep(0.2);
}
