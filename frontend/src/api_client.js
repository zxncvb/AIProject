import axios from "axios";

export const api = axios.create({ baseURL: "/", withCredentials: true });
let refreshPromise = null;

function csrfToken() {
  const item = document.cookie.split(";").map((value) => value.trim()).find((value) => value.startsWith("eai_csrf_token="));
  return item ? decodeURIComponent(item.slice("eai_csrf_token=".length)) : "";
}

api.interceptors.request.use((config) => {
  if (["post", "put", "patch", "delete"].includes((config.method || "").toLowerCase())) {
    const token = csrfToken();
    if (token) config.headers["X-CSRF-Token"] = token;
  }
  return config;
});

api.interceptors.response.use((response) => response, async (error) => {
  const request = error.config;
  if (error.response?.status !== 401 || request?._retry || request?.url?.includes("/api/auth/")) throw error;
  request._retry = true;
  refreshPromise ||= api.post("/api/auth/refresh", {}, { headers: { "X-Browser-Session": "1" } })
    .then(({ data }) => { localStorage.setItem("eai_session", "1"); return data; })
    .catch((refreshError) => { localStorage.removeItem("eai_session"); throw refreshError; })
    .finally(() => { refreshPromise = null; });
  await refreshPromise;
  return api(request);
});
