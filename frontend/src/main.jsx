import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import axios from "axios";
import { api } from "./api_client";
import { parseAgentSseFrames } from "./agent_stream";
import { Background, Controls, ReactFlow, addEdge, useEdgesState, useNodesState } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import "./styles.css";
import "./theme.css";
import "./extended.css";
import { ModelSquare, AgentStudio, Databases, PromptTemplates, QuickChat, Publishing, Approvals, AdminAnalytics, SecurityCenter } from "./product_pages";
import ModelExperience from "./model_experience";
import RunsCenter from "./runs_center";
import ApplicationsCenter from "./applications_center";
import DatabasePolicyEditor from "./database_policy";
import ProductionGovernance from "./production_governance";
import { WorkspaceCenter, ModelDetail, KnowledgeAssets, DatabaseCenter, PromptCenter, WorkflowGovernance, AgentLifecycle, AgentResources, AccountCenter, AdminResources, MarketCenter, ExtensionsControl, PublishingCenter, ApprovalCenter, PlatformConsole } from "./extended_pages";

const roleLabels = { owner: "所有者", admin: "管理员", developer: "开发者", editor: "编辑者", operator: "运营者", viewer: "查看者" };
const statusLabels = { draft: "草稿", published: "已发布", archived: "已归档", deployed: "已部署", indexing: "索引中", ready: "已就绪", pending: "待审批", approved: "已通过", rejected: "已拒绝", queued: "排队中", running: "运行中", waiting_approval: "等待审批", succeeded: "成功", failed: "失败", cancelled: "已取消", submitted: "已提交" };
const nodeLabels = { input: "输入", llm: "大模型", agent: "智能体", knowledge: "知识库", http: "接口请求", plugin: "插件", skill: "技能", approval: "人工审批", condition: "条件分支", loop: "循环", parallel: "并行", output: "输出" };

function errorText(error, fallback = "操作失败") {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (detail?.message) return detail.message;
  return fallback;
}
function browserCsrfToken() {
  const item = document.cookie.split(";").map((value) => value.trim()).find((value) => value.startsWith("eai_csrf_token="));
  return item ? decodeURIComponent(item.slice("eai_csrf_token=".length)) : "";
}
function formatDate(value) {
  if (!value) return "—";
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

function Login({ onLogin }) {
  const [email, setEmail] = useState("admin");
  const [password, setPassword] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  const [error, setError] = useState("");
  async function submit(event) {
    event.preventDefault();
    setError("");
    try {
      const { data } = await api.post("/api/auth/login", { email, password, mfa_code: mfaCode || null }, { headers: { "X-Browser-Session": "1" } });
      localStorage.setItem("eai_session", "1");
      onLogin(data);
    } catch (err) { setError(errorText(err, "登录失败，请检查账号和密码")); }
  }
  async function ldapLogin() {
    setError("");
    try {
      const { data } = await api.post("/api/auth/ldap/login", { email, password }, { headers: { "X-Browser-Session": "1" } });
      localStorage.setItem("eai_session", "1");
      onLogin(data);
    } catch (err) { setError(errorText(err, "LDAP 登录失败")); }
  }
  async function oidcLogin() {
    setError("");
    try {
      const { data } = await api.post("/api/auth/oidc/start", {});
      window.location.assign(data.authorization_url);
    } catch (err) { setError(errorText(err, "企业单点登录暂不可用")); }
  }
  return <main className="login-page"><form className="login-card" onSubmit={submit}>
    <div className="button-row"><button type="button" onClick={oidcLogin}>企业单点登录</button><button type="button" onClick={ldapLogin}>LDAP 登录</button></div>
    <div className="brand-mark">AI</div><div className="login-kicker">ENTERPRISE AI PLATFORM</div>
    <h1>企业 AI 中台</h1><p className="muted">统一管理模型、智能体、工作流、知识与企业权限。</p>
    <label>账号<input value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" /></label>
    <label>密码<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" /></label>
    <label>多因素验证码 <span className="label-hint">启用 MFA 后填写</span><input inputMode="numeric" value={mfaCode} onChange={(e) => setMfaCode(e.target.value)} placeholder="6 位验证码" /></label>
    {error && <div className="error">{error}</div>}<button className="primary full" type="submit">登录控制台</button><button type="button" onClick={() => window.location.assign("/reset-password")}>忘记密码</button><button type="button" onClick={() => window.location.assign("/verify-email")}>验证邮箱</button>
  </form></main>;
}

function PasswordReset() {
  const [email, setEmail] = useState("");
  const [token, setToken] = useState(() => new URLSearchParams(window.location.search).get("token") || "");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  async function request(event) {
    event.preventDefault(); setError(""); setMessage("");
    try {
      const { data } = await api.post("/api/auth/password-reset/request", { email });
      if (data.debug_token) setToken(data.debug_token);
      setMessage("如果账号存在，重置链接已发送；请检查邮箱。开发环境可直接使用返回的令牌。");
    } catch (err) { setError(errorText(err, "重置邮件请求失败")); }
  }
  async function confirm(event) {
    event.preventDefault(); setError(""); setMessage("");
    try {
      await api.post("/api/auth/password-reset/confirm", { token, new_password: password });
      setMessage("密码已重置，请返回登录。"); setPassword("");
    } catch (err) { setError(errorText(err, "重置令牌无效或已过期")); }
  }
  return <main className="login-page"><section className="login-card"><div className="brand-mark">AI</div><div className="login-kicker">ENTERPRISE AI PLATFORM</div><h1>重置密码</h1><form onSubmit={request}><label>账号邮箱<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></label><button className="primary full" type="submit">发送重置链接</button></form><form onSubmit={confirm}><label>重置令牌<input value={token} onChange={(e) => setToken(e.target.value)} minLength="32" required /></label><label>新密码<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} minLength="12" required /></label><button className="primary full" type="submit">确认新密码</button></form>{message && <div className="notice">{message}</div>}{error && <div className="error">{error}</div>}<button type="button" onClick={() => window.location.assign("/")}>返回登录</button></section></main>;
}

function EmailVerification() {
  const [email, setEmail] = useState("");
  const [token, setToken] = useState(() => new URLSearchParams(window.location.search).get("token") || "");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  async function request(event) {
    event.preventDefault(); setError(""); setMessage("");
    try {
      const { data } = await api.post("/api/auth/email-verification/request", { email });
      if (data.debug_token) setToken(data.debug_token);
      setMessage("如果账号存在，验证链接已发送；开发环境可直接使用返回的令牌。");
    } catch (err) { setError(errorText(err, "验证邮件请求失败")); }
  }
  async function confirm(event) {
    event.preventDefault(); setError(""); setMessage("");
    try {
      await api.post("/api/auth/email-verification/confirm", { token });
      setMessage("邮箱验证成功，请返回登录。");
    } catch (err) { setError(errorText(err, "邮箱验证令牌无效或已过期")); }
  }
  return <main className="login-page"><section className="login-card"><div className="brand-mark">AI</div><div className="login-kicker">ENTERPRISE AI PLATFORM</div><h1>验证邮箱</h1><form onSubmit={request}><label>账号邮箱<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></label><button className="primary full" type="submit">发送验证链接</button></form><form onSubmit={confirm}><label>验证令牌<input value={token} onChange={(e) => setToken(e.target.value)} minLength="32" required /></label><button className="primary full" type="submit">确认邮箱</button></form>{message && <div className="notice">{message}</div>}{error && <div className="error">{error}</div>}<button type="button" onClick={() => window.location.assign("/")}>返回登录</button></section></main>;
}

function PublicApplication({ tenantSlug, appSlug }) {
  const [runtime, setRuntime] = useState(null);
  const [form, setForm] = useState({});
  const [appKey, setAppKey] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const publicApi = axios.create({ baseURL: "/" });
  const schema = runtime?.runtime?.input_schema || {};
  const properties = Object.entries(schema.properties || {});

  useEffect(() => {
    let alive = true;
    publicApi.get(`/api/v1/public/apps/${encodeURIComponent(tenantSlug)}/${encodeURIComponent(appSlug)}`)
      .then(({ data }) => { if (alive) setRuntime(data); })
      .catch((err) => { if (alive) setError(errorText(err, "应用不存在或尚未发布")); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [tenantSlug, appSlug]);

  function setField(name, value, type) {
    if (type === "number" || type === "integer") {
      setForm((current) => ({ ...current, [name]: value === "" ? "" : Number(value) }));
      return;
    }
    setForm((current) => ({ ...current, [name]: value }));
  }

  async function invoke(event) {
    event.preventDefault(); setError(""); setResult(null); setRunning(true);
    try {
      const input = { ...form };
      for (const [name, definition] of properties) {
        if (["object", "array"].includes(definition?.type) && typeof input[name] === "string" && input[name].trim()) input[name] = JSON.parse(input[name]);
      }
      const headers = appKey ? { "X-App-Key": appKey } : {};
      const { data } = await publicApi.post(`/api/v1/public/apps/${encodeURIComponent(tenantSlug)}/${encodeURIComponent(appSlug)}/invoke`, { input }, { headers });
      if (data.status !== "queued" || !data.result_token) { setResult(data); return; }
      for (let attempt = 0; attempt < 60; attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
        const response = await publicApi.get(`/api/v1/public/runs/${encodeURIComponent(data.result_token)}`);
        setResult(response.data);
        if (["succeeded", "failed", "cancelled"].includes(response.data.status)) return;
      }
      setError("结果仍在执行，请稍后使用结果令牌继续查询。");
    } catch (err) { setError(err instanceof SyntaxError ? "对象/数组字段必须填写有效 JSON" : errorText(err, "应用调用失败")); }
    finally { setRunning(false); }
  }

  if (loading) return <main className="login-page"><section className="login-card"><div className="brand-mark">AI</div><h1>正在加载应用</h1></section></main>;
  return <main className="login-page"><section className="login-card" style={{ width: "min(680px, calc(100vw - 32px))" }}>
    <div className="brand-mark">AI</div><div className="login-kicker">PUBLIC APPLICATION</div>
    <h1>{runtime?.name || appSlug}</h1><p className="muted">{runtime?.runtime?.ui?.description || "填写表单后运行企业 AI 应用。"}</p>
    {runtime?.authentication_required && <label>应用调用密钥<input type="password" value={appKey} onChange={(event) => setAppKey(event.target.value)} autoComplete="off" required /></label>}
    <form className="form-grid" onSubmit={invoke}>
      {properties.map(([name, definition]) => {
        const type = definition?.type || "string";
        const label = definition?.title || definition?.label || name;
        const required = (schema.required || []).includes(name);
        if (["object", "array"].includes(type)) return <label key={name}>{label}<textarea value={form[name] || ""} onChange={(event) => setField(name, event.target.value, type)} placeholder={type === "array" ? "[]" : "{}"} required={required} /></label>;
        return <label key={name}>{label}<input type={type === "number" || type === "integer" ? "number" : type === "boolean" ? "checkbox" : "text"} value={type === "boolean" ? undefined : (form[name] ?? "")} checked={type === "boolean" ? Boolean(form[name]) : undefined} onChange={(event) => setField(name, type === "boolean" ? event.target.checked : event.target.value, type)} required={required} /></label>;
      })}
      {!properties.length && <div className="notice">该应用不需要输入参数。</div>}
      {error && <div className="error">{error}</div>}
      <button className="primary full" type="submit" disabled={running}>{running ? "运行中…" : "运行应用"}</button>
    </form>
    {result && <div className="notice"><b>运行状态：{statusLabels[result.status] || result.status}</b><pre className="json-view" style={{ marginTop: 10 }}>{JSON.stringify(result.output ?? result, null, 2)}</pre></div>}
  </section></main>;
}

const workspaceNav = [
  ["overview", "工作台", "⌂"], ["workspaces", "工作空间", "▣"], ["agents", "Agent 中心", "✦"], ["agent-studio", "Agent 编排", "✧"], ["agent-resources", "Agent 资源编排", "⊕"], ["agent-lifecycle", "Agent 生命周期", "↻"], ["applications", "应用中心", "▦"], ["workflows", "工作流", "⌘"], ["workflow-ops", "工作流治理", "✓"],
  ["models", "模型与算力", "◉"], ["model-experience", "模型体验", "▣"], ["model-square", "模型广场", "◇"], ["model-detail", "模型详情", "⌁"], ["knowledge", "知识库", "▤"], ["kb-assets", "知识库扩展", "◫"], ["databases", "数据库", "▥"], ["prompts", "提示词模板", "✎"], ["quick-chat", "快速对话", "☄"], ["extensions", "Skills / 插件", "◇"], ["explore", "探索中心", "☆"], ["runs", "运行与观测", "◌"]
];
const adminNav = [["members", "组织与权限", "♙"], ["publishing", "发布管理", "↗"], ["approvals", "审批中心", "✓"], ["production-governance", "生产治理", "⚙"], ["security", "安全与身份", "盾"], ["admin", "平台管理", "▦"], ["platform-resources", "平台资源管理", "▤"], ["account", "账号中心", "♙"], ["audit", "审计与治理", "≡"]];

function Layout({ me, page, setPage, onLogout, children }) {
  const current = [...workspaceNav, ...adminNav].find((item) => item[0] === page); const [workspaceName, setWorkspaceName] = useState(me?.tenant?.name || "示例企业");
  useEffect(() => { api.get("/api/workspaces").then((res) => { const selected = localStorage.getItem("eai_workspace_id"); const item = res.data.find((space) => space.id === selected) || res.data[0]; if (item) { setWorkspaceName(item.name); localStorage.setItem("eai_workspace_id", item.id); } }).catch(() => {}); const onChange = (event) => setWorkspaceName(event.detail?.name || workspaceName); window.addEventListener("workspace-change", onChange); return () => window.removeEventListener("workspace-change", onChange); }, [me?.tenant?.name]);
  return <div className="shell"><aside>
    <div className="logo"><span>AI</span><div><b>企业 AI 中台</b><small>Enterprise AI Platform</small></div></div>
    <div className="workspace-switcher" onClick={() => setPage("workspaces")}><small>当前工作区</small><strong>{workspaceName}</strong><span>⌄</span></div>
    <nav><div className="nav-caption">工作区</div>{workspaceNav.map(([id, label, icon]) => <button key={id} className={page === id ? "active" : ""} onClick={() => setPage(id)}><i>{icon}</i>{label}</button>)}<div className="nav-caption admin-caption">平台管理</div>{adminNav.map(([id, label, icon]) => <button key={id} className={page === id ? "active" : ""} onClick={() => setPage(id)}><i>{icon}</i>{label}</button>)}</nav>
    <div className="sidebar-bottom"><div className="user-chip"><div className="avatar">{(me?.user?.display_name || "A").slice(0, 1)}</div><div><b>{me?.user?.display_name || "平台管理员"}</b><small>{me?.user?.email || "admin"} · {roleLabels[me?.role] || "管理员"}</small></div></div><button className="logout" onClick={onLogout}>退出登录</button></div>
  </aside><section className="content"><header><div><span className="eyebrow">企业 AI 中台 / {current?.[1] || "工作台"}</span><h2>{current?.[1] || "工作台"}</h2></div><div className="header-right"><span className="status-dot">系统运行正常</span><button className="icon-btn" title="刷新页面" onClick={() => location.reload()}>↻</button></div></header>{children}</section></div>;
}

function PageTitle({ title, description, actions }) { return <div className="page-title"><div><h1>{title}</h1><p>{description}</p></div><div className="page-actions">{actions}</div></div>; }
function Panel({ title, subtitle, children, actions, className = "" }) { return <section className={`panel ${className}`}><div className="panel-head"><div><h3>{title}</h3>{subtitle && <small>{subtitle}</small>}</div>{actions}</div>{children}</section>; }
function Modal({ title, children, onClose, className = "" }) { return <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><section className={`modal-card ${className}`} role="dialog" aria-modal="true" aria-label={title}><div className="modal-head"><h2>{title}</h2><button type="button" className="modal-close" aria-label="关闭" onClick={onClose}>×</button></div>{children}</section></div>; }
function Stat({ label, value, detail, tone = "blue" }) { return <div className={`stat ${tone}`}><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>; }
function StatusTag({ value, tone }) { return <span className={`tag ${tone || (value === "已发布" || value === "已通过" || value === "已就绪" ? "green" : value === "待审批" || value === "索引中" ? "yellow" : "")}`}>{statusLabels[value] || value || "未知"}</span>; }
function Empty({ text }) { return <div className="empty">{text}</div>; }

function Overview({ data, go }) {
  const quick = [["agents", "创建 Agent", "配置一个可复用的企业助手"], ["workflows", "设计工作流", "编排模型、知识和审批节点"], ["knowledge", "建立知识库", "上传企业文档并进行检索"], ["models", "接入模型", "配置 OpenAI 兼容模型提供商"]];
  return <div className="page"><div className="home-banner"><div><span className="eyebrow light">AI PLATFORM / WORKSPACE</span><h1>把企业 AI 能力变成可交付的软件资产</h1><p>统一管理模型、Agent、工作流、知识库、插件和生产运行证据。</p></div><div className="banner-meta"><b>生产环境</b><small>多租户隔离 · 权限可审计</small></div></div>
    <div className="stat-grid"><Stat label="Agent" value={data.agents.length} detail="可复用智能体"/><Stat label="工作流" value={data.workflows.length} detail="版本化编排资产"/><Stat label="知识库" value={data.kbs.length} detail="企业知识空间"/><Stat label="近期运行" value={data.runs.length} detail="可追溯运行记录" tone="purple"/></div>
    <div className="two-col"><Panel title="快速开始" subtitle="从一个真实业务场景开始构建"><div className="quick-grid">{quick.map(([id, title, desc]) => <button className="quick-card" key={id} onClick={() => go(id)}><span>{id === "agents" ? "✦" : id === "workflows" ? "⌘" : id === "knowledge" ? "▤" : "◉"}</span><div><b>{title}</b><small>{desc}</small></div><em>→</em></button>)}</div></Panel><Panel title="平台健康度" subtitle="当前工作区资源概览"><div className="health-list"><div><span>模型提供商</span><b>{data.models.length ? "已接入" : "待配置"}</b><StatusTag value={data.models.length ? "已就绪" : "待配置"}/></div><div><span>知识检索</span><b>{data.kbs.length ? "可用" : "待建立"}</b><StatusTag value={data.kbs.length ? "已就绪" : "待配置"}/></div><div><span>扩展能力</span><b>{data.skills.length + data.plugins.length + data.mcp.length} 个</b><StatusTag value="已就绪"/></div><div><span>系统权限</span><b>租户级隔离</b><StatusTag value="已就绪"/></div></div></Panel></div>
  </div>;
}

function Agents({ data, refresh }) {
  const [agents, setAgents] = useState(data.agents || []);
  const [workspaces, setWorkspaces] = useState([]);
  const [selected, setSelected] = useState("");
  const [message, setMessage] = useState("");
  const [answer, setAnswer] = useState("");
  const [question, setQuestion] = useState("");
  const [toolTrace, setToolTrace] = useState([]);
  const [citations, setCitations] = useState([]);
  const [conversationId, setConversationId] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [importFile, setImportFile] = useState(null);
  const abortRef = useRef(null);
  const [form, setForm] = useState({ name: "企业智能助手", slug: `assistant-${Date.now()}`, description: "面向企业员工的知识问答助手", system_prompt: "你是一名企业智能助手，请基于企业知识和权限边界回答问题。", provider_id: "", knowledge_base_id: "", workspace_id: "", agent_type: "chat" });

  async function reload() { try { const res = await api.get("/api/agents"); setAgents(res.data); } catch (err) { setMessage(errorText(err, "Agent 列表读取失败")); } }
  useEffect(() => { reload(); api.get("/api/workspaces").then((res) => { setWorkspaces(res.data); if (!form.workspace_id && res.data[0]) setForm((current) => ({ ...current, workspace_id: res.data[0].id })); }).catch(() => {}); }, []);
  useEffect(() => { abortRef.current?.abort(); abortRef.current = null; setStreaming(false); setConversationId(""); setAnswer(""); setToolTrace([]); setCitations([]); }, [selected]);
  useEffect(() => () => abortRef.current?.abort(), []);

  async function create(event) {
    event.preventDefault();
    try {
      const res = await api.post("/api/agents", { ...form, project_id: data.projects[0]?.id, provider_id: form.provider_id || null, knowledge_base_id: form.knowledge_base_id || null, workspace_id: form.workspace_id || null });
      await api.patch(`/api/agents/${res.data.id}/config`, { agent_type: form.agent_type, workspace_id: form.workspace_id || null, prompt_template: form.system_prompt, variables: [], memory: {}, capabilities: {}, experience: {}, safety: {} });
      setSelected(res.data.id); setCreateOpen(false); setMessage("Agent 已创建并完成基础配置"); await reload(); await refresh();
    } catch (err) { setMessage(errorText(err, "Agent 创建失败")); }
  }
  async function importAgent(event) {
    event.preventDefault();
    if (!importFile) return;
    try { const payload = JSON.parse(await importFile.text()); await api.post("/api/agents/import", { ...payload, project_id: data.projects[0]?.id }); setImportFile(null); setImportOpen(false); setMessage("Agent 已导入"); await reload(); await refresh(); } catch (err) { setMessage(errorText(err, "Agent 导入失败，请检查 JSON 文件")); }
  }
  async function removeAgent(agent) { if (window.prompt("请输入智能体名称，以确认删除") !== agent.name) return; try { await api.delete(`/api/agents/${agent.id}`); if (selected === agent.id) { setSelected(""); setAnswer(""); } setMessage(`Agent「${agent.name}」已删除`); await reload(); await refresh(); } catch (err) { setMessage(errorText(err, "Agent 删除失败")); } }
  async function chat() {
    if (streaming) return;
    setStreaming(true); setToolTrace([]); setCitations([]); setMessage(""); setAnswer("");
    const controller = new AbortController(); abortRef.current = controller;
    try {
      const response = await fetch(`/api/agents/${selected}/chat/stream`, { method: "POST", credentials: "include", signal: controller.signal, headers: { "Content-Type": "application/json", "X-CSRF-Token": browserCsrfToken() }, body: JSON.stringify({ message: question, conversation_id: conversationId || null }) });
      if (!response.ok) { let detail = "Agent 调用失败，请先配置模型"; try { const payload = await response.json(); detail = payload.detail?.message || payload.detail || detail; } catch (_) {} throw new Error(detail); }
      if (!response.body) throw new Error("Agent 流式响应不可用");
      const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = ""; let text = "";
      const handleEvents = (events) => events.forEach(({ event, payload }) => {
        if (event === "token") { text += payload.text || ""; setAnswer(text); }
        if (event === "tool_call") { setToolTrace((items) => [...items, { type: event, ...payload }]); setMessage(`正在调用工具：${payload.name || "未命名工具"}`); }
        if (event === "tool_result") setToolTrace((items) => [...items, { type: event, ...payload }]);
        if (event === "done") { setConversationId(payload.conversation_id || ""); setAnswer(payload.text || text); setCitations(Array.isArray(payload.citations) ? payload.citations : []); setMessage("Agent 已完成"); }
        if (event === "error") throw new Error(payload.message || "Agent 流式调用失败");
      });
      while (true) { const { value, done } = await reader.read(); if (done) break; buffer += decoder.decode(value, { stream: true }); const parsed = parseAgentSseFrames(buffer); buffer = parsed.buffer; handleEvents(parsed.events); }
      buffer += decoder.decode(); handleEvents(parseAgentSseFrames(buffer, true).events); setQuestion("");
    } catch (err) { setMessage(err.name === "AbortError" ? "Agent 流式请求已取消" : (err.message || "Agent 调用失败")); } finally { setStreaming(false); abortRef.current = null; }
  }
  function cancelChat() { abortRef.current?.abort(); }
  const selectedAgent = agents.find((agent) => agent.id === selected);
  return <div className="page">
    <PageTitle title="Agent 中心" description="创建、配置、测试和发布可复用的企业智能体。" actions={<><button onClick={() => setImportOpen(true)}>导入 Agent</button><button className="primary" onClick={() => setCreateOpen(true)}>+ 创建 Agent</button></>}/>
    <div className="feature-strip agent-feature-strip"><div><b>本地 Agent</b><small>{agents.length} 个可复用智能体</small></div><div><b>知识增强</b><small>绑定企业知识库和访问权限</small></div><div><b>工具治理</b><small>插件、Skill、MCP 审批后调用</small></div><div><b>运行可追溯</b><small>流式输出、工具轨迹和反馈</small></div></div>
    <div className="sub-tabs"><button className="active">本地 Agent <b>{agents.length}</b></button><button>A2A 服务 <b>0</b></button><div className="table-tools"><input placeholder="搜索 Agent"/><button>筛选</button></div></div>
    <div className="agent-layout"><Panel title="Agent 资产" subtitle="选择一个智能体进入测试工作台" className="asset-panel"><div className="card-grid">{agents.map((agent) => <article className={`asset-card ${selected === agent.id ? "selected" : ""}`} key={agent.id} role="button" tabIndex={0} onClick={() => setSelected(agent.id)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") setSelected(agent.id); }}><div className="asset-icon">✦</div><div className="asset-card-body"><div className="card-title"><b>{agent.name}</b><button type="button" className="delete-button asset-delete" onClick={(event) => { event.stopPropagation(); removeAgent(agent); }}>删除</button></div><p>{agent.description || "企业智能助手"}</p><small>v{agent.version || 1} · {agent.provider_id ? "已绑定模型" : "未绑定模型"}</small><div><StatusTag value={agent.enabled ? "已就绪" : "已停用"}/></div></div></article>)}</div>{!agents.length && <Empty text="还没有 Agent，请点击右上角创建。"/>}</Panel>
      <Panel title="测试工作台" subtitle={selectedAgent ? `${selectedAgent.name} · ${selectedAgent.agent_type || "对话型"}` : "先选择一个 Agent"} className="agent-editor"><div className="chat-box"><div className="section-label">实时对话 {selected ? "· 已选择 Agent" : "· 请先选择 Agent"}</div><div className="search-row"><input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="例如：公司差旅报销标准是什么？"/><button disabled={!selected || !question.trim()} onClick={streaming ? cancelChat : chat}>{streaming ? "取消" : "发送"}</button></div>{toolTrace.length > 0 && <div className="tool-trace"><div className="section-label">工具调用轨迹</div>{toolTrace.map((item, index) => <div className="tool-trace-item" key={`${item.type}-${item.id || item.name || index}`}><span>{item.type === "tool_call" ? "调用" : "结果"}</span><b>{item.name || "未命名工具"}</b><small>{item.status || "已完成"}</small></div>)}</div>}{answer && <article className="answer"><b>Agent 回复</b><p>{answer}</p>{citations.length > 0 && <div className="citation-list"><small>知识来源</small>{citations.map((citation) => <span key={`${citation.index}-${citation.chunk_id || citation.document_id}`}>[{citation.index}] {citation.source || citation.document_id || citation.chunk_id}</span>)}</div>}</article>}{!answer && <div className="chat-placeholder">发送问题后，在这里查看流式回答、工具轨迹和知识引用。</div>}</div></Panel>
    </div>{message && <div className="notice">{message}</div>}
    {createOpen && <Modal title="创建智能体" onClose={() => setCreateOpen(false)} className="modal-wide"><form className="modal-form" onSubmit={create}><div className="agent-type-grid"><label className={form.agent_type === "chat" ? "selected" : ""}><input type="radio" checked={form.agent_type === "chat"} onChange={() => setForm({ ...form, agent_type: "chat" })}/><b>对话型</b><small>一问一答，适合企业知识问答和日常助手。</small></label><label className={form.agent_type === "chatflow" ? "selected" : ""}><input type="radio" checked={form.agent_type === "chatflow"} onChange={() => setForm({ ...form, agent_type: "chatflow" })}/><b>对话流型</b><small>连续对话并结合工具、知识和工作流。</small></label></div><div className="modal-form-grid"><label>工作空间<select value={form.workspace_id} onChange={(event) => setForm({ ...form, workspace_id: event.target.value })}><option value="">不指定工作空间</option>{workspaces.map((space) => <option value={space.id} key={space.id}>{space.name}</option>)}</select></label><label>模型提供商<select value={form.provider_id} onChange={(event) => setForm({ ...form, provider_id: event.target.value })}><option value="">自动选择已启用模型</option>{data.models.map((model) => <option value={model.id} key={model.id}>{model.name} / {model.default_model}</option>)}</select></label><label>名称<input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} required maxLength={128}/></label><label>唯一标识<input value={form.slug} onChange={(event) => setForm({ ...form, slug: event.target.value })} required/></label><label>知识库<select value={form.knowledge_base_id} onChange={(event) => setForm({ ...form, knowledge_base_id: event.target.value })}><option value="">不绑定知识库</option>{data.kbs.map((kb) => <option value={kb.id} key={kb.id}>{kb.name}</option>)}</select></label><label>功能说明<input value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })}/></label></div><label>系统提示词<textarea value={form.system_prompt} onChange={(event) => setForm({ ...form, system_prompt: event.target.value })} required/></label><div className="modal-actions"><button type="button" onClick={() => setCreateOpen(false)}>取消</button><button className="primary">创建</button></div></form></Modal>}
    {importOpen && <Modal title="导入智能体" onClose={() => setImportOpen(false)}><form className="modal-form" onSubmit={importAgent}><div className="upload-dropzone"><input id="agent-import-file" type="file" accept=".json,application/json" onChange={(event) => setImportFile(event.target.files?.[0] || null)}/><label htmlFor="agent-import-file"><b>选择 Agent JSON 文件</b><small>{importFile ? importFile.name : "支持导入已导出的企业智能体配置"}</small></label></div><div className="modal-actions"><button type="button" onClick={() => setImportOpen(false)}>取消</button><button className="primary" disabled={!importFile}>导入</button></div></form></Modal>}
  </div>;
}

function AgentsLegacy({ data, refresh }) {
  const [toolTrace, setToolTrace] = useState([]); const [streaming, setStreaming] = useState(false); const abortRef = useRef(null);
  const [agents, setAgents] = useState(data.agents || []); const [selected, setSelected] = useState(""); const [message, setMessage] = useState(""); const [answer, setAnswer] = useState(""); const [conversationId, setConversationId] = useState(""); const [citations, setCitations] = useState([]);
  const [workspaces, setWorkspaces] = useState([]); const [importFile, setImportFile] = useState(null);
  const [form, setForm] = useState({ name: "企业智能助手", slug: `assistant-${Date.now()}`, description: "面向企业员工的知识问答助手", system_prompt: "你是一名企业智能助手，请基于企业知识和权限边界回答问题。", provider_id: "", knowledge_base_id: "", workspace_id: "", agent_type: "chat" }); const [question, setQuestion] = useState("");
  useEffect(() => { abortRef.current?.abort(); abortRef.current = null; setStreaming(false); setConversationId(""); setAnswer(""); setToolTrace([]); setCitations([]); }, [selected]);
  useEffect(() => () => abortRef.current?.abort(), []);
  async function reload() { try { const res = await api.get("/api/agents"); setAgents(res.data); } catch (err) { setMessage(errorText(err, "Agent 列表读取失败")); } }
  useEffect(() => { reload(); api.get("/api/workspaces").then((res) => { setWorkspaces(res.data); if (!form.workspace_id && res.data[0]) setForm((current) => ({ ...current, workspace_id: res.data[0].id })); }).catch(() => {}); }, []);
  async function create(event) { event.preventDefault(); try { const res = await api.post("/api/agents", { ...form, project_id: data.projects[0]?.id, provider_id: form.provider_id || null, knowledge_base_id: form.knowledge_base_id || null, workspace_id: form.workspace_id || null }); await api.patch(`/api/agents/${res.data.id}/config`, { agent_type: form.agent_type, workspace_id: form.workspace_id || null, prompt_template: form.system_prompt, variables: [], memory: {}, capabilities: {}, experience: {}, safety: {} }); setSelected(res.data.id); setMessage("Agent 已创建并完成工作空间配置"); await reload(); await refresh(); } catch (err) { setMessage(errorText(err, "Agent 创建失败")); } }
  async function importAgent() { if (!importFile) return; try { const payload = JSON.parse(await importFile.text()); await api.post("/api/agents/import", { ...payload, project_id: data.projects[0]?.id }); setImportFile(null); setMessage("Agent 已导入"); await reload(); await refresh(); } catch (err) { setMessage(errorText(err, "Agent 导入失败，请检查 JSON")); } }
  async function removeAgent(agent) { if (window.prompt("请输入智能体名称，以确认删除") !== agent.name) return; try { await api.delete("/api/agents/" + agent.id); if (selected === agent.id) { setSelected(""); setAnswer(""); } setMessage("Agent「" + agent.name + "」已删除"); await reload(); await refresh(); } catch (err) { setMessage(errorText(err, "Agent 删除失败")); } }
  async function chat() {
    if (streaming) return;
    setStreaming(true); setToolTrace([]);
    const controller = new AbortController(); abortRef.current = controller;
    setMessage(""); setAnswer(""); setCitations([]);
    try {
      const response = await fetch(`/api/agents/${selected}/chat/stream`, { method: "POST", credentials: "include", signal: controller.signal, headers: { "Content-Type": "application/json", "X-CSRF-Token": browserCsrfToken() }, body: JSON.stringify({ message: question, conversation_id: conversationId || null }) });
      if (!response.ok) { let detail = "Agent 调用失败，请先配置模型"; try { const payload = await response.json(); detail = payload.detail?.message || payload.detail || detail; } catch (_) {} throw new Error(detail); }
      if (!response.body) throw new Error("Agent 流式响应不可用");
      const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = ""; let text = "";
      const handleEvents = (events) => events.forEach(({ event, payload }) => {
        if (event === "token") { text += payload.text || ""; setAnswer(text); }
        if (event === "tool_call") { setToolTrace((items) => [...items, { type: event, ...payload }]); setMessage(`正在调用工具：${payload.name || "未命名工具"}`); }
        if (event === "tool_result") { setToolTrace((items) => [...items, { type: event, ...payload }]); }
        if (event === "done") { setConversationId(payload.conversation_id || ""); setAnswer(payload.text || text); setCitations(Array.isArray(payload.citations) ? payload.citations : []); setMessage("Agent 已完成"); }
        if (event === "error") throw new Error(payload.message || "Agent 流式调用失败");
      });
      while (true) {
        const { value, done } = await reader.read(); if (done) break; buffer += decoder.decode(value, { stream: true });
        const parsed = parseAgentSseFrames(buffer); buffer = parsed.buffer; handleEvents(parsed.events);
      }
      buffer += decoder.decode(); handleEvents(parseAgentSseFrames(buffer, true).events);
      setQuestion(""); setStreaming(false); abortRef.current = null;
    } catch (err) { setMessage(err.name === "AbortError" ? "Agent 流式请求已取消" : (err.message || "Agent 调用失败，请先配置模型")); setStreaming(false); abortRef.current = null; }
  }
  function cancelChat() { abortRef.current?.abort(); }
  return <div className="page"><PageTitle title="Agent 中心" description="创建、配置、测试和发布可复用的企业智能体。" actions={<><label className="file-button">选择导入文件<input type="file" accept=".json" onChange={(e) => setImportFile(e.target.files[0])}/></label><button onClick={importAgent} disabled={!importFile}>导入 Agent</button><button className="primary" onClick={() => document.getElementById("agent-create")?.scrollIntoView({ behavior: "smooth" })}>+ 创建 Agent</button></>}/>
    <div className="sub-tabs"><button className="active">本地 Agent <b>{agents.length}</b></button><button>我的收藏 <b>0</b></button><div className="table-tools"><input placeholder="搜索 Agent"/><button>筛选</button></div></div>
    <div className="agent-layout"><Panel title="Agent 资产" subtitle={`${agents.length} 个智能体，支持模型和知识库绑定`} className="asset-panel"><div className="card-grid">{agents.map((agent) => <article className={`asset-card ${selected === agent.id ? "selected" : ""}`} key={agent.id} role="button" tabIndex={0} onClick={() => setSelected(agent.id)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") setSelected(agent.id); }}><div className="asset-icon">✦</div><div className="asset-card-body"><div className="card-title"><b>{agent.name}</b><button type="button" className="delete-button asset-delete" title="删除 Agent" onClick={(event) => { event.stopPropagation(); removeAgent(agent); }}>删除</button></div><p>{agent.description || "企业智能助手"}</p><small>v{agent.version || 1} · {agent.provider_id ? "已绑定模型" : "未绑定模型"}</small><div><StatusTag value={agent.enabled ? "已就绪" : "已停用"}/></div></div></article>)}</div>{!agents.length && <Empty text="还没有 Agent，请从右侧创建第一个企业智能体。"/>}</Panel>
      <Panel title="创建 / 测试 Agent" subtitle="先选择类型和工作空间，再绑定模型进行真实对话测试" className="agent-editor"><form id="agent-create" className="form-grid" onSubmit={create}><label>名称<input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required/></label><label>唯一标识<input value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value })} required/></label><label>智能体类型<select value={form.agent_type} onChange={(e) => setForm({ ...form, agent_type: e.target.value })}><option value="chat">对话型</option><option value="chatflow">对话流型</option></select></label><label>工作空间<select value={form.workspace_id} onChange={(e) => setForm({ ...form, workspace_id: e.target.value })}><option value="">不指定工作空间</option>{workspaces.map((space) => <option value={space.id} key={space.id}>{space.name}</option>)}</select></label><label>模型提供商<select value={form.provider_id} onChange={(e) => setForm({ ...form, provider_id: e.target.value })}><option value="">自动选择已启用模型</option>{data.models.map((model) => <option value={model.id} key={model.id}>{model.name} / {model.default_model}</option>)}</select></label><label>知识库<select value={form.knowledge_base_id} onChange={(e) => setForm({ ...form, knowledge_base_id: e.target.value })}><option value="">不绑定知识库</option>{data.kbs.map((kb) => <option value={kb.id} key={kb.id}>{kb.name}</option>)}</select></label><label>系统提示词<textarea value={form.system_prompt} onChange={(e) => setForm({ ...form, system_prompt: e.target.value })} required/></label><button className="primary" type="submit">创建 Agent</button></form><div className="chat-box"><div className="section-label">对话测试 {selected ? "· 已选择 Agent" : "· 请先选择 Agent"}</div><div className="search-row"><input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="例如：公司差旅报销标准是什么？"/><button disabled={!selected || !question.trim() || streaming} onClick={streaming ? cancelChat : chat}>{streaming ? "取消" : "发送"}</button></div>{toolTrace.length > 0 && <div className="tool-trace"><div className="section-label">工具调用轨迹</div>{toolTrace.map((item, index) => <div className="tool-trace-item" key={`${item.type}-${item.id || item.name || index}`}><span>{item.type === "tool_call" ? "调用" : "结果"}</span><b>{item.name || "未命名工具"}</b><small>{item.status || "进行中"}</small></div>)}</div>}{answer && <article className="answer"><b>Agent 回复</b><p>{answer}</p></article>}</div>{message && <div className="notice">{message}</div>}</Panel></div>
  </div>;
}

function Applications({ data, refresh }) {
  const [message, setMessage] = useState(""); const [selected, setSelected] = useState(null); const [form, setForm] = useState({ name: "企业 AI 应用", slug: `app-${Date.now()}`, app_type: "low_code", description: "", runtime: "{}", source: "{}" });
  async function create(event) { event.preventDefault(); try { const res = await api.post("/api/applications", { ...form, project_id: data.projects[0]?.id, runtime: JSON.parse(form.runtime || "{}"), source: JSON.parse(form.source || "{}") }); await api.post(`/api/applications/${res.data.id}/deploy`); setMessage("应用已创建并发布"); setForm({ ...form, name: "", slug: `app-${Date.now()}` }); await refresh(); } catch (err) { setMessage(errorText(err, "应用创建失败，请检查 JSON 配置")); } }
  async function deploy(app) { try { await api.post(`/api/applications/${app.id}/deploy`); setMessage(`${app.name} 已发布`); await refresh(); } catch (err) { setMessage(errorText(err, "应用发布失败")); } }
  return <div className="page"><PageTitle title="应用中心" description="将低代码和全代码能力沉淀为可发布、可运营的企业应用。" actions={<><button>应用模板</button><button className="primary" onClick={() => document.getElementById("app-form")?.scrollIntoView({ behavior: "smooth" })}>+ 创建应用</button></>}/><div className="sub-tabs"><button className="active">全部应用 <b>{data.applications.length}</b></button><button>低代码</button><button>全代码</button><div className="table-tools"><input placeholder="搜索应用"/><button>筛选</button></div></div><div className="app-grid">{data.applications.map((app) => <article className="app-card" key={app.id} onClick={() => setSelected(app)}><div className="app-card-top"><div className="asset-icon app-icon">{app.app_type === "low_code" ? "▦" : "{ }"}</div><StatusTag value={app.status}/></div><h3>{app.name}</h3><p>{app.description || "企业 AI 应用"}</p><small>{app.app_type === "low_code" ? "低代码应用" : "全代码应用"} · {app.slug}</small><div className="card-actions"><button onClick={(e) => { e.stopPropagation(); deploy(app); }}>发布</button><button onClick={(e) => { e.stopPropagation(); setSelected(app); }}>详情</button></div></article>)}{!data.applications.length && <Empty text="还没有应用，请创建第一个可发布应用。"/>}</div><div className="two-col app-bottom"><Panel title="创建应用" subtitle="创建后会生成初始版本" className="wide-panel"><form id="app-form" className="form-grid" onSubmit={create}><label>应用名称<input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required/></label><label>唯一标识<input value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value })} required/></label><label>应用类型<select value={form.app_type} onChange={(e) => setForm({ ...form, app_type: e.target.value })}><option value="low_code">低代码</option><option value="full_code">全代码</option></select></label><label>描述<textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })}/></label><label>运行时配置 JSON<textarea value={form.runtime} onChange={(e) => setForm({ ...form, runtime: e.target.value })}/></label><label>页面源码 JSON<textarea value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })}/></label><button className="primary">创建并发布</button></form>{message && <div className="notice">{message}</div>}</Panel>{selected && <ApplicationDetail app={selected} onClose={() => setSelected(null)}/>}</div></div>;
}

function ApplicationDetail({ app, onClose }) { const [detail, setDetail] = useState(null); useEffect(() => { api.get(`/api/applications/${app.id}`).then((res) => setDetail(res.data)); }, [app.id]); return <Panel title="应用详情" subtitle={app.name} actions={<button onClick={onClose}>关闭</button>}><div className="detail-summary"><b>{app.name}</b><StatusTag value={app.status}/><span>{app.app_type === "low_code" ? "低代码" : "全代码"}</span></div><h4>版本历史</h4><div className="table compact-table">{(detail?.versions || []).map((version) => <div className="table-row" key={version.id}><b>v{version.version}</b><span>{version.status}</span><span>{formatDate(version.created_at)}</span></div>)}</div>{!detail && <small>正在读取版本信息…</small>}</Panel>; }

const defaultGraph = { nodes: [{ id: "start", type: "default", position: { x: 40, y: 120 }, data: { kind: "input", label: "输入 / 开始" } }, { id: "llm", type: "default", position: { x: 320, y: 120 }, data: { kind: "llm", label: "大模型", system: "你是企业 AI 助手", prompt: "{{input.question}}" } }, { id: "end", type: "default", position: { x: 620, y: 120 }, data: { kind: "output", label: "输出 / 结束" } }], edges: [{ id: "e1", source: "start", target: "llm" }, { id: "e2", source: "llm", target: "end" }] };

function Workflows({ data, refresh }) {
  const [workflowItems, setWorkflowItems] = useState(data.workflows); const [selected, setSelected] = useState(null); const [nodes, setNodes, onNodesChange] = useNodesState([]); const [edges, setEdges, onEdgesChange] = useEdgesState([]); const [nodeType, setNodeType] = useState("knowledge"); const [question, setQuestion] = useState("请总结企业当前的 AI 建设重点"); const [message, setMessage] = useState(""); const [validation, setValidation] = useState(null); const [schedules, setSchedules] = useState([]); const [busyAction, setBusyAction] = useState("");
  useEffect(() => { setWorkflowItems(data.workflows); }, [data.workflows]);
  useEffect(() => { if (selected) { setNodes(selected.graph?.nodes || defaultGraph.nodes); setEdges(selected.graph?.edges || defaultGraph.edges); } }, [selected, setNodes, setEdges]);
  async function create() { const name = window.prompt("请输入工作流名称", "新工作流 " + (workflowItems.length + 1))?.trim(); if (!name || busyAction) return; setBusyAction("create"); try { const inputSchema = { question: { type: "string", required: true } }; const res = await api.post("/api/workflows", { project_id: data.projects[0]?.id, name, slug: "workflow-" + Date.now(), graph: defaultGraph, input_schema: inputSchema, changelog: "初始版本" }); const summary = { ...res.data, project_id: data.projects[0]?.id, graph: defaultGraph, input_schema: inputSchema }; setWorkflowItems((items) => [summary, ...items.filter((item) => item.id !== summary.id)]); setSelected(summary); setMessage("工作流已创建"); await refresh(); } catch (err) { setMessage(errorText(err, "工作流创建失败")); } finally { setBusyAction(""); } }
  async function rename(workflow) { const name = window.prompt("请输入新的工作流名称", workflow.name)?.trim(); if (!name || name === workflow.name || busyAction) return; setBusyAction("rename"); try { await api.patch("/api/workflows/" + workflow.id, { name }); setWorkflowItems((items) => items.map((item) => item.id === workflow.id ? { ...item, name } : item)); setSelected((item) => item?.id === workflow.id ? { ...item, name } : item); await refresh(); setMessage("工作流已改名"); } catch (err) { setMessage(errorText(err, "工作流改名失败")); } finally { setBusyAction(""); } }
  async function open(id) { try { const res = await api.get(`/api/workflows/${id}`); setSelected(res.data); setValidation(null); const schedulesRes = await api.get(`/api/workflows/${id}/schedules`); setSchedules(schedulesRes.data); } catch (err) { setSchedules([]); setMessage(errorText(err, "工作流读取失败")); } }
  async function save() { try { await api.post(`/api/workflows/${selected.id}/versions`, { graph: { nodes, edges }, input_schema: selected.input_schema || {}, changelog: "控制台编辑" }); setMessage("已保存新版本"); await refresh(); await open(selected.id); } catch (err) { setMessage(errorText(err, "版本保存失败")); } }
  async function validate() { try { const res = await api.post(`/api/workflows/${selected.id}/validate`); setValidation(res.data); setMessage(res.data.valid ? "工作流校验通过" : "工作流存在校验问题"); } catch (err) { setMessage(errorText(err, "工作流校验失败")); } }
  async function publish() { try { await api.post(`/api/workflows/${selected.id}/publish`); setMessage("工作流已发布"); await refresh(); await open(selected.id); } catch (err) { setMessage(errorText(err, "工作流发布失败")); } }
  async function release() { try { await api.post(`/api/workflows/${selected.id}/release`, { environment: "production" }); setMessage("生产发布已提交"); await refresh(); await open(selected.id); } catch (err) { setMessage(errorText(err, "生产发布失败")); } }
  async function run() { try { const res = await api.post(`/api/workflows/${selected.id}/runs`, { input: { question }, environment: "dev" }); setMessage(`运行已提交：${res.data.run_id?.slice(0, 8) || "已进入队列"}`); } catch (err) { setMessage(errorText(err, "工作流运行失败")); } }
  async function remove(workflow) { if (!window.confirm(`确定删除工作流“${workflow.name}”吗？删除后版本和运行记录也会删除。`)) return; setBusyAction(`delete:${workflow.id}`); try { await api.delete(`/api/workflows/${workflow.id}`); setWorkflowItems((items) => items.filter((item) => item.id !== workflow.id)); if (selected?.id === workflow.id) { setSelected(null); setNodes([]); setEdges([]); setSchedules([]); setValidation(null); } setMessage("工作流已删除"); await refresh(); } catch (err) { setMessage(errorText(err, "删除失败")); } finally { setBusyAction(""); } }
  function addNode() { const id = `${nodeType}-${Date.now()}`; setNodes((items) => [...items, { id, type: "default", position: { x: 180 + items.length * 35, y: 280 }, data: { kind: nodeType, label: `${nodeLabels[nodeType]} 节点` } }]); }
  return <div className="page"><PageTitle title="工作流" description="用可视化节点编排模型、Agent、知识库、插件和人工审批。" actions={<button className="primary" disabled={busyAction === "create"} onClick={create}>{busyAction === "create" ? "创建中…" : "+ 新建工作流"}</button>}/><div className="workflow-layout"><Panel title="工作流资产" subtitle={`${workflowItems.length} 个工作流`} className="workflow-list"><div className="list">{workflowItems.map((item) => <div className="list-item-row" key={item.id}><button className={`list-item ${selected?.id === item.id ? "selected" : ""}`} onClick={() => open(item.id)}><span className="list-icon">⌘</span><span><b>{item.name}</b><small>{statusLabels[item.status] || item.status} · v{item.latest_version || 1}</small></span></button><button className="workflow-rename" disabled={Boolean(busyAction)} onClick={() => rename(item)}>改名</button><button className="delete-button" disabled={Boolean(busyAction)} title="删除工作流" onClick={() => remove(item)}>×</button></div>)}</div>{!workflowItems.length && <Empty text="还没有工作流。"/>}</Panel><Panel title={selected ? selected.name : "工作流编辑器"} subtitle={selected ? `v${selected.latest_version || 1} · ${statusLabels[selected.status] || selected.status}` : "选择一个工作流或创建新的工作流"} actions={selected && <div className="button-row"><button onClick={() => rename(selected)}>改名</button><button onClick={save}>保存版本</button><button onClick={publish}>发布</button><button className="primary" onClick={run}>测试运行</button></div>} className="workflow-editor">{selected ? <><div className="node-toolbar"><div className="node-palette">{["input", "llm", "agent", "knowledge", "plugin", "approval", "condition", "output"].map((item) => <button className={nodeType === item ? "active" : ""} key={item} onClick={() => setNodeType(item)}>{nodeLabels[item]}</button>)}</div><button onClick={addNode}>添加节点</button><input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="测试输入"/></div><div className="flow"><ReactFlow nodes={nodes} edges={edges} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onConnect={(connection) => setEdges((items) => addEdge(connection, items))} fitView><Background variant="dots" gap={18} size={1}/><Controls/></ReactFlow></div><div className="run-console"><div><b>调试控制台</b><small>运行结果和节点日志会显示在这里</small></div><span className="tag">开发环境</span></div>{message && <div className="notice">{message}</div>}</> : <Empty text="选择左侧工作流开始编辑，或者点击右上角新建工作流。"/>}</Panel></div></div>;
}

function Models({ data, refresh }) {
  const blankForm = { name: "", provider_type: "openai_compatible", base_url: "https://api.openai.com/v1", default_model: "gpt-4o-mini", api_key: "", enabled: true };
  const [form, setForm] = useState({ ...blankForm, name: "OpenAI 兼容模型" }); const [editing, setEditing] = useState(null); const [message, setMessage] = useState(""); const [route, setRoute] = useState(null);
  async function submit(event) { event.preventDefault(); try { const payload = { name: form.name, provider_type: form.provider_type, base_url: form.base_url, default_model: form.default_model, enabled: Boolean(form.enabled), config: { priority: 100 } }; if (form.api_key.trim()) payload.api_key = form.api_key.trim(); if (editing) { await api.patch(`/api/models/${editing}`, payload); setMessage("模型提供商已更新"); } else { await api.post("/api/models", { ...payload, api_key: form.api_key }); setMessage("模型提供商已保存"); } setEditing(null); setForm({ ...blankForm }); await refresh(); } catch (err) { setMessage(errorText(err, editing ? "模型更新失败" : "模型保存失败")); } }
  function editModel(model) { setEditing(model.id); setForm({ name: model.name, provider_type: model.provider_type, base_url: model.base_url, default_model: model.default_model, api_key: "", enabled: model.enabled }); document.getElementById("model-form")?.scrollIntoView({ behavior: "smooth", block: "center" }); }
  function cancelEdit() { setEditing(null); setForm({ ...blankForm }); setMessage(""); }
  async function test(model, kind = "health") { try { const res = await api.post(`/api/models/${model.id}/test`, { prompt: kind === "embedding" ? "企业知识库向量测试" : "ping", kind }); setMessage(`${model.name}：${res.data.detail || "检测完成"}，延迟 ${res.data.latency_ms || 0} ms`); } catch (err) { setMessage(errorText(err, "模型检测失败")); } }
  async function loadRoute() { try { const res = await api.get("/api/models/route"); setRoute(res.data); } catch (err) { setMessage(errorText(err, "路由状态读取失败")); } }
  return <div className="page"><PageTitle title="模型与算力" description="接入模型提供商，查看能力、健康度和租户算力配额。" actions={<><button onClick={loadRoute}>查看路由</button><button className="primary" onClick={() => { cancelEdit(); document.getElementById("model-form")?.scrollIntoView({ behavior: "smooth" }); }}>+ 接入模型</button></>}/><div className="feature-strip"><div><b>模型体验</b><small>调用验证和延迟测试</small></div><div><b>模型广场</b><small>企业可用模型清单</small></div><div><b>智能路由</b><small>健康检查与优先级</small></div><div><b>算力配额</b><small>Token / GPU / 并发</small></div></div><div className="two-col"><Panel title="已接入模型" subtitle={`${data.models.length} 个提供商`}><div className="model-cards">{data.models.map((model) => <article className="model-card" key={model.id}><div className="model-logo">◉</div><div className="model-main"><div className="card-title"><b>{model.name}</b><StatusTag value={model.enabled ? "已就绪" : "已停用"}/></div><p>{model.default_model}</p><small>{model.base_url}</small><div className="button-row"><button onClick={() => editModel(model)}>编辑</button><button onClick={() => test(model)}>健康检测</button><button onClick={() => test(model, "chat")}>聊天检测</button></div></div></article>)}</div>{!data.models.length && <Empty text="尚未配置模型。配置后 Agent 和工作流才能进行真实调用。"/>}{route?.selected && <div className="notice">当前路由：{route.selected.name} / {route.selected.model}</div>}{message && <div className="notice">{message}</div>}</Panel><Panel title={editing ? "编辑模型提供商" : "接入模型提供商"} subtitle={editing ? "修改连接参数；API Key 留空表示保留现有密钥" : "支持 OpenAI 兼容接口"}><form id="model-form" className="form-grid" onSubmit={submit}><label>提供商名称<input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required/></label><label>接口类型<select value={form.provider_type} onChange={(e) => setForm({ ...form, provider_type: e.target.value })}><option value="openai_compatible">OpenAI 兼容</option><option value="azure_openai">Azure OpenAI</option><option value="qwen">阿里云百炼</option></select></label><label>接口地址<input value={form.base_url} onChange={(e) => setForm({ ...form, base_url: e.target.value })} required/></label><label>默认模型<input value={form.default_model} onChange={(e) => setForm({ ...form, default_model: e.target.value })} required/></label><label>API Key<input type="password" value={form.api_key} onChange={(e) => setForm({ ...form, api_key: e.target.value })} placeholder={editing ? "留空表示保留现有密钥" : "仅写入后端加密字段"}/></label><label className="checkbox-label"><input type="checkbox" checked={Boolean(form.enabled)} onChange={(e) => setForm({ ...form, enabled: e.target.checked })}/> 启用模型</label><div className="button-row"><button className="primary">{editing ? "保存修改" : "保存模型"}</button>{editing && <button type="button" onClick={cancelEdit}>取消编辑</button>}</div></form></Panel></div><ComputeQuota/></div>;
}

function ComputeQuota() { const [quota, setQuota] = useState(null); const [message, setMessage] = useState(""); useEffect(() => { api.get("/api/compute/quota").then((res) => setQuota(res.data)).catch((err) => setMessage(errorText(err, "配额读取失败"))); }, []); async function save(event) { event.preventDefault(); try { await api.put("/api/compute/quota", quota); setMessage("算力配额已保存"); } catch (err) { setMessage(errorText(err, "配额保存失败")); } } if (!quota) return <Panel title="算力配额" subtitle={message || "正在读取租户配额…"} />; return <Panel title="算力配额" subtitle="租户级 CPU、内存、GPU、并发和 Token 限额"><form className="quota-grid" onSubmit={save}><label>CPU 毫核<input type="number" min="100" value={quota.cpu_millicores} onChange={(e) => setQuota({ ...quota, cpu_millicores: Number(e.target.value) })}/></label><label>内存 MB<input type="number" min="128" value={quota.memory_mb} onChange={(e) => setQuota({ ...quota, memory_mb: Number(e.target.value) })}/></label><label>并发运行数<input type="number" min="1" value={quota.concurrent_runs} onChange={(e) => setQuota({ ...quota, concurrent_runs: Number(e.target.value) })}/></label><label>GPU 数量<input type="number" min="0" value={quota.gpu_count} onChange={(e) => setQuota({ ...quota, gpu_count: Number(e.target.value) })}/></label><label>月 Token 配额<input type="number" min="1000" value={quota.monthly_tokens} onChange={(e) => setQuota({ ...quota, monthly_tokens: Number(e.target.value) })}/></label><label><input type="checkbox" checked={Boolean(quota.enabled)} onChange={(e) => setQuota({ ...quota, enabled: e.target.checked })}/> 启用算力配额</label><button className="primary">保存配额</button></form>{message && <div className="notice">{message}</div>}</Panel>; }

function Knowledge({ data, refresh }) {
  const [selected, setSelected] = useState(data.kbs[0]?.id || "");
  const [tab, setTab] = useState("files");
  const [kbName, setKbName] = useState("");
  const [kbDescription, setKbDescription] = useState("企业知识空间");
  const [file, setFile] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [message, setMessage] = useState("");
  const [creating, setCreating] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadReport, setUploadReport] = useState(null);
  const currentKb = data.kbs.find((kb) => kb.id === selected);

  async function loadDocs(id = selected) { if (!id) return; try { const res = await api.get(`/api/knowledge-bases/${id}/documents`); setDocuments(res.data); } catch (err) { setMessage(errorText(err, "文档读取失败")); } }
  useEffect(() => { if (data.kbs.length && (!selected || !data.kbs.some((item) => item.id === selected))) setSelected(data.kbs[0].id); }, [data.kbs, selected]);
  useEffect(() => { loadDocs(); }, [selected]);
  function selectKnowledgeBase(kb) { setSelected(kb.id); setTab("files"); setResults([]); setMessage(`已打开“${kb.name}”`); loadDocs(kb.id); }
  async function renameKnowledgeBase(kb) { const name = window.prompt("请输入新的知识库名称", kb.name)?.trim(); if (!name || name === kb.name) return; try { await api.patch(`/api/knowledge-bases/${kb.id}`, { name }); setMessage("知识库已改名"); await refresh(); } catch (err) { setMessage(errorText(err, "知识库改名失败")); } }
  async function create(event) {
    event.preventDefault(); const name = kbName.trim();
    if (!name || !data.projects[0]?.id) return;
    const existing = data.kbs.find((item) => item.project_id === data.projects[0].id && item.name.trim().toLowerCase() === name.toLowerCase());
    if (existing) { selectKnowledgeBase(existing); setCreateOpen(false); setMessage(`“${name}”已存在，已为你打开`); return; }
    setCreating(true);
    try { const res = await api.post("/api/knowledge-bases", { project_id: data.projects[0].id, name, description: kbDescription }); setSelected(res.data.id); setKbName(""); setCreateOpen(false); setMessage(`知识库“${name}”已创建`); await refresh(); } catch (err) { setMessage(errorText(err, "知识库创建失败")); } finally { setCreating(false); }
  }
  async function upload(event) {
    event.preventDefault(); if (!file || !selected) return; setUploading(true); setUploadReport(null);
    try { const body = new FormData(); body.append("file", file); const res = await api.post(`/api/knowledge-bases/${selected}/documents`, body); const report = res.data.security_report || {}; setUploadReport({ title: file.name, method: res.data.extraction_method || "文本解析", findings: report.dlp_findings?.length || 0, status: res.data.status || "ready" }); setMessage(`“${file.name}”已完成解析并建立索引`); setFile(null); setUploadOpen(false); await loadDocs(); } catch (err) { setMessage(errorText(err, "文档上传失败")); } finally { setUploading(false); }
  }
  async function search() { try { const res = await api.get(`/api/knowledge-bases/${selected}/search`, { params: { q: query, mode: "hybrid" } }); setResults(res.data.results || []); } catch (err) { setMessage(errorText(err, "检索失败")); } }
  return <div className="page">
    <PageTitle title="知识库" description="管理企业文档、解析任务、检索命中和知识访问权限。" actions={<button className="primary" type="button" onClick={() => setCreateOpen(true)}>+ 新建知识库</button>}/>
    <div className="feature-strip"><div><b>文档解析</b><small>PDF、Office、文本、图片 OCR</small></div><div><b>安全处理</b><small>敏感信息扫描和权限隔离</small></div><div><b>混合检索</b><small>关键词、向量和重排结合</small></div><div><b>可追溯引用</b><small>Agent 回答返回知识来源</small></div></div>
    <div className="knowledge-layout"><Panel title="知识库资产" subtitle={`${data.kbs.length} 个知识空间`}><div className="list">{data.kbs.map((kb) => <div className="list-item-row knowledge-list-row" key={kb.id}><button type="button" aria-pressed={selected === kb.id} className={`list-item ${selected === kb.id ? "selected" : ""}`} onClick={() => selectKnowledgeBase(kb)}><span className="list-icon">▤</span><span><b>{kb.name}</b><small>{kb.description || "企业知识空间"}</small></span></button><button type="button" className="knowledge-rename" onClick={() => renameKnowledgeBase(kb)}>改名</button></div>)}</div>{!data.kbs.length && <Empty text="还没有知识库，请点击右上角创建。"/>}</Panel>
      <Panel title={currentKb?.name || "知识库详情"} subtitle={selected ? "文件、命中测试和配置" : "请选择左侧知识库"} className="knowledge-detail">{selected ? <><div className="knowledge-summary"><div><b>{currentKb?.name}</b><small>{documents.length} 个文档 · 当前租户授权范围</small></div><StatusTag value={documents.length ? "已就绪" : "待配置"}/></div><div className="sub-tabs detail-tabs"><button className={tab === "files" ? "active" : ""} onClick={() => setTab("files")}>文件列表 <b>{documents.length}</b></button><button className={tab === "hit" ? "active" : ""} onClick={() => setTab("hit")}>命中测试</button><button className={tab === "settings" ? "active" : ""} onClick={() => setTab("settings")}>设置详情</button></div>{tab === "files" && <><div className="detail-toolbar"><div><b>企业文档</b><small>上传后自动安全解析、切片并建立索引</small></div><button className="primary" onClick={() => setUploadOpen(true)}>上传文件</button></div>{uploadReport && <div className="upload-success"><b>最近上传：{uploadReport.title}</b><span>解析方式：{uploadReport.method} · {uploadReport.findings ? `发现 ${uploadReport.findings} 项敏感信息` : "未发现敏感信息"}</span></div>}<div className="table document-table"><div className="table-head"><span>文件名称</span><span>解析方式</span><span>安全状态</span><span>创建时间</span></div>{documents.map((doc) => <div className="table-row" key={doc.id}><b>{doc.title}</b><span>{doc.extraction_method || doc.source || "文本解析"}</span><StatusTag value={doc.security_status === "clean" ? "已就绪" : doc.security_status || doc.status}/><span>{formatDate(doc.created_at)}</span></div>)}</div>{!documents.length && <Empty text="还没有文档，请点击上传文件。"/>}</>}{tab === "hit" && <><div className="search-row"><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="输入问题测试召回结果"/><button disabled={!query.trim()} onClick={search}>检索</button></div><div className="results">{results.map((item) => <article key={item.chunk_id}><span>相关度 {Number(item.score || 0).toFixed(3)} · {item.source || "hybrid"}</span><p>{item.content}</p></article>)}</div>{!results.length && <Empty text="输入问题后查看知识库命中片段。"/>}</>}{tab === "settings" && <div className="settings-grid"><div><b>检索模式</b><span>混合检索 + 向量召回 + 重排</span></div><div><b>访问范围</b><span>当前工作区与知识库授权</span></div><div><b>处理能力</b><span>PDF、Office、文本、图片 OCR、安全扫描与 DLP</span></div></div>}</> : <Empty text="请选择一个知识库查看详情。"/>}</Panel>
    </div>{message && <div className="notice">{message}</div>}
    {createOpen && <Modal title="创建知识库" onClose={() => setCreateOpen(false)}><form className="modal-form" onSubmit={create}><div className="step-indicator"><span className="active">1</span><b>基本配置</b><i></i><span>2</span><b>设置类型</b></div><label>知识库名称<input autoFocus value={kbName} onChange={(event) => setKbName(event.target.value)} placeholder="给知识库起一个名字吧" maxLength={128} required/></label><label>知识库描述<textarea value={kbDescription} onChange={(event) => setKbDescription(event.target.value)} placeholder="对该知识库进行描述，帮助团队理解内容范围"/></label><div className="modal-option selected"><input type="radio" checked readOnly/><div><b>标准知识库</b><small>管理平台里的企业知识库，支持文档解析和混合检索。</small></div></div><div className="modal-actions"><button type="button" onClick={() => setCreateOpen(false)}>取消</button><button className="primary" disabled={creating || !kbName.trim()}>{creating ? "创建中…" : "创建"}</button></div></form></Modal>}
    {uploadOpen && <Modal title="上传并解析文件" onClose={() => { if (!uploading) setUploadOpen(false); }} className="modal-upload"><form className="modal-form" onSubmit={upload}><div className="upload-dropzone"><input id="knowledge-upload-file" type="file" accept=".txt,.md,.json,.csv,.log,.pdf,.docx,.xlsx,.xlsm,.png,.jpg,.jpeg,.webp,.tif,.tiff" onChange={(event) => setFile(event.target.files?.[0] || null)}/><label htmlFor="knowledge-upload-file"><b>{file ? file.name : "选择或拖拽文件到这里"}</b><small>{file ? `${(file.size / 1024 / 1024).toFixed(2)} MB · 等待解析` : "支持 PDF、Word、Excel、Markdown、图片等企业资料"}</small></label></div><div className="format-list"><div><b>文档</b><span>pdf、doc、docx、ppt、pptx、xls、xlsx、txt、md、json</span></div><div><b>图片</b><span>png、jpg、jpeg、webp、tif、tiff</span></div></div><div className="modal-actions"><button type="button" disabled={uploading} onClick={() => setUploadOpen(false)}>取消</button><button className="primary" disabled={uploading || !file}>{uploading ? "解析中…" : "上传并解析"}</button></div></form></Modal>}
  </div>;
}

function KnowledgeLegacy({ data, refresh }) {
  const [selected, setSelected] = useState(data.kbs[0]?.id || ""); const [tab, setTab] = useState("files"); const [kbName, setKbName] = useState(""); const [file, setFile] = useState(null); const [documents, setDocuments] = useState([]); const [query, setQuery] = useState(""); const [results, setResults] = useState([]); const [message, setMessage] = useState(""); const [creating, setCreating] = useState(false);
  async function loadDocs(id = selected) { if (!id) return; try { const res = await api.get(`/api/knowledge-bases/${id}/documents`); setDocuments(res.data); } catch (err) { setMessage(errorText(err, "文档读取失败")); } }
  useEffect(() => { if (data.kbs.length && (!selected || !data.kbs.some((item) => item.id === selected))) setSelected(data.kbs[0].id); }, [data.kbs, selected]); useEffect(() => { loadDocs(); }, [selected]);
  function selectKnowledgeBase(kb) { setSelected(kb.id); setTab("files"); setResults([]); setMessage(`已打开“${kb.name}”`); loadDocs(kb.id); }
  async function renameKnowledgeBase(kb) { const name = window.prompt("请输入新的知识库名称", kb.name)?.trim(); if (!name || name === kb.name) return; try { await api.patch(`/api/knowledge-bases/${kb.id}`, { name }); setMessage("知识库已改名"); await refresh(); } catch (err) { setMessage(errorText(err, "知识库改名失败")); } }
  function focusCreate() { document.getElementById("knowledge-base-name")?.focus(); document.getElementById("knowledge-base-name")?.select(); }
  async function create() {
    const name = kbName.trim();
    if (!name) { setMessage("请输入知识库名称"); focusCreate(); return; }
    if (!data.projects[0]?.id) { setMessage("当前没有可用项目，请先创建项目"); return; }
    const existing = data.kbs.find((item) => item.project_id === data.projects[0].id && item.name.trim().toLowerCase() === name.toLowerCase());
    if (existing) { selectKnowledgeBase(existing); setMessage(`“${name}”已存在，已为你打开`); return; }
    setCreating(true);
    try { const res = await api.post("/api/knowledge-bases", { project_id: data.projects[0].id, name, description: "企业知识空间" }); setSelected(res.data.id); setKbName(""); setMessage(`知识库“${name}”已创建`); await refresh(); } catch (err) { setMessage(errorText(err, "知识库创建失败")); } finally { setCreating(false); }
  }
  async function upload() { if (!file || !selected) return; try { const body = new FormData(); body.append("file", file); const res = await api.post(`/api/knowledge-bases/${selected}/documents`, body); setFile(null); const report = res.data.security_report || {}; setMessage(`文档已安全解析并建立索引（${res.data.extraction_method || "文本解析"}${report.dlp_findings?.length ? `，发现 ${report.dlp_findings.length} 项敏感信息` : "，未发现敏感信息"}）`); await loadDocs(); } catch (err) { setMessage(errorText(err, "文档上传失败")); } }
  async function search() { try { const res = await api.get(`/api/knowledge-bases/${selected}/search`, { params: { q: query, mode: "hybrid" } }); setResults(res.data.results || []); } catch (err) { setMessage(errorText(err, "检索失败")); } }
  return <div className="page"><PageTitle title="知识库" description="管理企业文档、解析任务、检索命中和知识访问权限。" actions={<button className="primary" type="button" onClick={focusCreate}>+ 新建知识库</button>}/><div className="knowledge-layout"><Panel title="知识库资产" subtitle={`${data.kbs.length} 个知识空间`}><div className="list">{data.kbs.map((kb) => <div className="list-item-row knowledge-list-row" key={kb.id}><button type="button" aria-pressed={selected === kb.id} className={`list-item ${selected === kb.id ? "selected" : ""}`} onClick={() => selectKnowledgeBase(kb)}><span className="list-icon">▤</span><span><b>{kb.name}</b><small>{kb.description || "企业知识空间"}</small></span></button><button type="button" className="knowledge-rename" onClick={() => renameKnowledgeBase(kb)}>改名</button></div>)}</div><div className="inline-form"><input id="knowledge-base-name" value={kbName} onChange={(e) => setKbName(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") create(); }} placeholder="输入新知识库名称"/><button type="button" disabled={creating || !kbName.trim()} onClick={create}>{creating ? "创建中…" : "新建"}</button></div>{!data.kbs.length && <Empty text="还没有知识库。"/>}</Panel><Panel title={data.kbs.find((kb) => kb.id === selected)?.name || "知识库详情"} subtitle={selected ? "文件、命中测试和配置" : "请选择左侧知识库"} className="knowledge-detail">{selected ? <><div className="sub-tabs detail-tabs"><button className={tab === "files" ? "active" : ""} onClick={() => setTab("files")}>文件列表 <b>{documents.length}</b></button><button className={tab === "hit" ? "active" : ""} onClick={() => setTab("hit")}>命中测试</button><button className={tab === "settings" ? "active" : ""} onClick={() => setTab("settings")}>设置详情</button></div>{tab === "files" && <><div className="upload"><input type="file" accept=".txt,.md,.json,.csv,.log,.pdf,.docx,.xlsx,.xlsm,.png,.jpg,.jpeg,.webp,.tif,.tiff" onChange={(e) => setFile(e.target.files[0])}/><button disabled={!file} onClick={upload}>上传并安全解析</button></div><div className="table document-table"><div className="table-head"><span>文件名称</span><span>解析方式</span><span>安全状态</span><span>创建时间</span></div>{documents.map((doc) => <div className="table-row" key={doc.id}><b>{doc.title}</b><span>{doc.extraction_method || doc.source}</span><StatusTag value={doc.security_status === "clean" ? "已就绪" : doc.security_status || doc.status}/><span>{formatDate(doc.created_at)}</span></div>)}</div>{!documents.length && <Empty text="还没有文档，请上传企业资料。"/>}</>}{tab === "hit" && <><div className="search-row"><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="输入问题测试召回结果"/><button disabled={!query.trim()} onClick={search}>检索</button></div><div className="results">{results.map((item) => <article key={item.chunk_id}><span>相关度 {Number(item.score || 0).toFixed(3)}</span><p>{item.content}</p></article>)}</div>{!results.length && <Empty text="输入问题后查看知识库命中片段。"/>}</>}{tab === "settings" && <div className="settings-grid"><div><b>检索模式</b><span>混合检索 + 向量召回</span></div><div><b>访问范围</b><span>当前工作区与知识库授权</span></div><div><b>处理能力</b><span>PDF、Office、文本、图片 OCR、安全扫描与 DLP</span></div></div>}</> : <Empty text="请选择一个知识库查看详情。"/>}</Panel></div>{message && <div className="notice">{message}</div>}</div>;
}

function Extensions({ data, refresh }) {
  const [tab, setTab] = useState("plugins"); const [message, setMessage] = useState(""); const [skill, setSkill] = useState({ name: "", version: "1.0.0", description: "", instructions: "" }); const [plugin, setPlugin] = useState({ name: "", endpoint: "", kind: "http", manifest: "{}" });
  async function saveSkill(event) { event.preventDefault(); try { await api.post("/api/skills", { ...skill, project_id: data.projects[0]?.id, manifest: {} }); setSkill({ name: "", version: "1.0.0", description: "", instructions: "" }); setMessage("Skill 已注册"); await refresh(); } catch (err) { setMessage(errorText(err, "Skill 注册失败")); } }
  async function savePlugin(event) { event.preventDefault(); try { await api.post("/api/plugins", { ...plugin, manifest: JSON.parse(plugin.manifest || "{}") }); setPlugin({ name: "", endpoint: "", kind: "http", manifest: "{}" }); setMessage("插件已注册，等待审批"); await refresh(); } catch (err) { setMessage(errorText(err, "插件注册失败，请检查 JSON")); } }
  async function approve(pluginId, action) { try { await api.post(`/api/plugins/${pluginId}/${action}`); setMessage(action === "approve" ? "插件已通过审批" : "插件已拒绝"); await refresh(); } catch (err) { setMessage(errorText(err, "审批操作失败")); } }
  return <div className="page"><PageTitle title="Skills / 插件" description="通过可复用指令、企业工具和 MCP 服务扩展 Agent 能力。" actions={<button className="primary">能力市场</button>}/><div className="sub-tabs"><button className={tab === "plugins" ? "active" : ""} onClick={() => setTab("plugins")}>插件 <b>{data.plugins.length}</b></button><button className={tab === "skills" ? "active" : ""} onClick={() => setTab("skills")}>Skills <b>{data.skills.length}</b></button><button className={tab === "mcp" ? "active" : ""} onClick={() => setTab("mcp")}>MCP 服务 <b>{data.mcp.length}</b></button></div>{tab === "plugins" && <div className="two-col"><Panel title="插件资产" subtitle="插件必须通过审批后才能被调用"><div className="table"><div className="table-head"><span>名称</span><span>类型</span><span>审批状态</span><span>操作</span></div>{data.plugins.map((item) => <div className="table-row" key={item.id}><b>{item.name}</b><span>{item.kind}</span><StatusTag value={item.approval_status}/><div className="button-row">{item.approval_status === "pending" && <><button onClick={() => approve(item.id, "approve")}>通过</button><button onClick={() => approve(item.id, "reject")}>拒绝</button></>}</div></div>)}</div>{!data.plugins.length && <Empty text="还没有注册插件。"/>}</Panel><Panel title="注册插件" subtitle="HTTP 插件由后端白名单和能力清单保护"><form className="form-grid" onSubmit={savePlugin}><label>插件名称<input value={plugin.name} onChange={(e) => setPlugin({ ...plugin, name: e.target.value })} required/></label><label>接口地址<input value={plugin.endpoint} onChange={(e) => setPlugin({ ...plugin, endpoint: e.target.value })} required/></label><label>能力清单 JSON<textarea value={plugin.manifest} onChange={(e) => setPlugin({ ...plugin, manifest: e.target.value })}/></label><button className="primary">注册插件</button></form></Panel></div>}{tab === "skills" && <div className="two-col"><Panel title="Skills 资产" subtitle="版本化的企业指令包"><div className="table">{data.skills.map((item) => <div className="table-row" key={item.id}><b>{item.name}</b><span>v{item.version}</span><span>{item.description || "可复用指令"}</span><StatusTag value={item.enabled ? "已就绪" : "已停用"}/></div>)}</div></Panel><Panel title="注册 Skill"><form className="form-grid" onSubmit={saveSkill}><label>名称<input value={skill.name} onChange={(e) => setSkill({ ...skill, name: e.target.value })} required/></label><label>版本<input value={skill.version} onChange={(e) => setSkill({ ...skill, version: e.target.value })}/></label><label>说明<input value={skill.description} onChange={(e) => setSkill({ ...skill, description: e.target.value })}/></label><label>指令内容<textarea value={skill.instructions} onChange={(e) => setSkill({ ...skill, instructions: e.target.value })} required/></label><button className="primary">注册 Skill</button></form></Panel></div>}{tab === "mcp" && <Panel title="MCP 服务" subtitle="统一登记外部工具服务"><div className="table"><div className="table-head"><span>服务名称</span><span>传输方式</span><span>地址</span><span>状态</span></div>{data.mcp.map((item) => <div className="table-row" key={item.id}><b>{item.name}</b><span>{item.transport}</span><span>{item.endpoint}</span><StatusTag value={item.enabled ? "已就绪" : "已停用"}/></div>)}</div>{!data.mcp.length && <Empty text="还没有登记 MCP 服务。"/>}</Panel>}{message && <div className="notice">{message}</div>}</div>;
}

function RunsLegacy({ data }) { const [selected, setSelected] = useState(null); function exportRuns() { const blob = new Blob([JSON.stringify(data.runs, null, 2)], { type: "application/json;charset=utf-8" }); const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = "enterprise-ai-runs.json"; link.click(); URL.revokeObjectURL(url); } return <div className="page"><PageTitle title="运行与观测" description="查看工作流和 Agent 的执行状态、耗时、成本与错误。" actions={<button onClick={exportRuns}>导出运行记录</button>}/><div className="stat-grid"><Stat label="总运行数" value={data.runs.length} detail="当前租户"/><Stat label="成功率" value="—" detail="等待真实运行数据" tone="green"/><Stat label="平均延迟" value="—" detail="节点级统计" tone="purple"/><Stat label="Token 成本" value="—" detail="FinOps 统计"/></div><Panel title="运行记录" subtitle="最近的执行任务"><div className="table run-table"><div className="table-head"><span>运行 ID</span><span>资源</span><span>状态</span><span>开始时间</span><span>操作</span></div>{data.runs.map((run) => <div className="table-row" key={run.id} onClick={() => setSelected(run)}><b>{run.id.slice(0, 12)}</b><span>{run.workflow_id || run.agent_id || "—"}</span><StatusTag value={run.status}/><span>{formatDate(run.created_at)}</span><button>查看详情</button></div>)}</div>{!data.runs.length && <Empty text="还没有运行记录。发布工作流或调用 Agent 后，这里会出现执行详情。"/>}</Panel>{selected && <Panel title="运行详情" subtitle={selected.id} actions={<button onClick={() => setSelected(null)}>关闭</button>}><pre className="json-view">{JSON.stringify(selected, null, 2)}</pre></Panel>}</div>; }

function Runs({ data }) {
  const [selected, setSelected] = useState(null);
  const [summary, setSummary] = useState(null);
  useEffect(() => { api.get("/api/observability/summary").then((res) => setSummary(res.data)).catch(() => setSummary(null)); }, [data.runs.length]);
  function exportRuns() {
    const blob = new Blob([JSON.stringify(data.runs, null, 2)], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob); const link = document.createElement("a");
    link.href = url; link.download = "enterprise-ai-runs.json"; link.click(); URL.revokeObjectURL(url);
  }
  const successRate = summary ? `${(Number(summary.success_rate_30d || 0) * 100).toFixed(1)}%` : "—";
  const avgLatency = summary ? `${summary.avg_latency_ms_30d || 0} ms` : "—";
  const p95Latency = summary ? `P95 ${summary.p95_latency_ms_30d || 0} ms` : "等待数据";
  return <div className="page"><PageTitle title="运行与观测" description="查看工作流和 Agent 的执行状态、耗时、成本与错误。" actions={<button onClick={exportRuns}>导出运行记录</button>}/><div className="stat-grid"><Stat label="总运行数" value={summary?.total_runs ?? data.runs.length} detail="当前租户"/><Stat label="近 30 天成功率" value={successRate} detail={`${summary?.recent_runs || 0} 次运行`} tone="green"/><Stat label="平均延迟" value={avgLatency} detail={p95Latency} tone="purple"/><Stat label="Token 用量" value={summary?.usage?.tokens ?? "—"} detail="FinOps 统计"/></div><Panel title="运行记录" subtitle="最近的执行任务"><div className="table run-table"><div className="table-head"><span>运行 ID</span><span>资源</span><span>状态</span><span>开始时间</span><span>操作</span></div>{data.runs.map((run) => <div className="table-row" key={run.id} onClick={() => setSelected(run)}><b>{run.id.slice(0, 12)}</b><span>{run.workflow_id || run.agent_id || "—"}</span><StatusTag value={run.status}/><span>{formatDate(run.created_at)}</span><button type="button">查看详情</button></div>)}</div>{!data.runs.length && <Empty text="还没有运行记录。发布工作流或调用 Agent 后，这里会出现执行详情。"/>}</Panel>{selected && <Panel title="运行详情" subtitle={selected.id} actions={<button onClick={() => setSelected(null)}>关闭</button>}><pre className="json-view">{JSON.stringify(selected, null, 2)}</pre></Panel>}</div>;
}

function Members({ me }) { const [members, setMembers] = useState([]); const [message, setMessage] = useState(""); const [form, setForm] = useState({ email: "", display_name: "", password: "", role: "viewer" }); async function load() { try { const res = await api.get("/api/members"); setMembers(res.data); } catch (err) { setMessage(errorText(err, "成员读取失败")); } } useEffect(() => { load(); }, []); async function create(event) { event.preventDefault(); try { await api.post("/api/members", form); setMessage("成员已添加"); setForm({ email: "", display_name: "", password: "", role: "viewer" }); await load(); } catch (err) { setMessage(errorText(err, "成员添加失败")); } } if (!["owner", "admin"].includes(me?.role)) return <div className="page"><Empty text="只有租户管理员可以管理组织成员。"/></div>; return <div className="page"><PageTitle title="组织与权限" description="管理成员、角色和租户级资源访问边界。" actions={<button className="primary" onClick={() => document.getElementById("member-form")?.scrollIntoView({ behavior: "smooth" })}>+ 添加成员</button>}/><div className="two-col"><Panel title="租户成员" subtitle={`${members.length} 位成员`}><div className="table"><div className="table-head"><span>成员</span><span>角色</span><span>状态</span><span>操作</span></div>{members.map((member) => <div className="table-row" key={member.user_id}><div><b>{member.display_name || member.email}</b><small>{member.email}</small></div><span>{roleLabels[member.role] || member.role}</span><StatusTag value={member.is_active ? "已就绪" : "已停用"}/><span>—</span></div>)}</div></Panel><Panel title="添加成员" subtitle="初始密码至少 12 位"><form id="member-form" className="form-grid" onSubmit={create}><label>邮箱<input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required/></label><label>显示名称<input value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} required/></label><label>初始密码<input type="password" minLength="12" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required/></label><label>角色<select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>{Object.entries(roleLabels).filter(([role]) => role !== "owner").map(([role, label]) => <option value={role} key={role}>{label}</option>)}</select></label><button className="primary">添加成员</button></form>{message && <div className="notice">{message}</div>}</Panel></div></div>; }

function Security({ me }) { const [mfa, setMfa] = useState(Boolean(me?.user?.mfa_enabled)); const [secret, setSecret] = useState(null); const [code, setCode] = useState(""); const [message, setMessage] = useState(""); async function setup() { try { const res = await api.post("/api/me/mfa/setup"); setSecret(res.data); } catch (err) { setMessage(errorText(err, "MFA 配置失败")); } } async function enable() { try { await api.post("/api/me/mfa/enable", { code }); setMfa(true); setSecret(null); setMessage("MFA 已启用"); } catch (err) { setMessage(errorText(err, "验证码校验失败")); } } return <div className="page"><PageTitle title="安全与身份" description="配置 MFA、SCIM 和企业身份系统接入。"/><div className="two-col"><Panel title="多因素认证 MFA" subtitle="为当前账号启用 TOTP"><div className="security-status"><span className="security-icon">盾</span><div><b>{mfa ? "MFA 已启用" : "MFA 尚未启用"}</b><small>{mfa ? "登录时需要额外验证码" : "建议为管理员账号开启"}</small></div><StatusTag value={mfa ? "已就绪" : "待配置"}/></div>{!mfa && <><button className="primary" onClick={setup}>生成 MFA 密钥</button>{secret && <div className="notice"><code>{secret.secret}</code><div className="search-row"><input inputMode="numeric" placeholder="输入 6 位验证码" value={code} onChange={(e) => setCode(e.target.value)}/><button onClick={enable}>启用 MFA</button></div></div>}</>}</Panel><Panel title="企业身份系统" subtitle="统一身份、用户同步和单点登录"><div className="identity-list"><div><b>OIDC / SAML</b><span>配置企业单点登录</span><StatusTag value="待配置"/></div><div><b>LDAP</b><span>连接企业目录服务</span><StatusTag value="待配置"/></div><div><b>SCIM</b><span>同步 Azure AD、阿里云 IDaaS 或 Keycloak 用户</span><StatusTag value="已就绪"/></div></div></Panel></div>{message && <div className="notice">{message}</div>}</div>; }

function Audit({ data }) { return <div className="page"><PageTitle title="审计与治理" description="保留关键资源变更、发布和权限操作证据。" actions={<button onClick={() => window.open("/api/audit/export", "_blank")}>导出审计日志</button>}/><Panel title="审计日志" subtitle={`${data.audit.length} 条记录`}><div className="table"><div className="table-head"><span>时间</span><span>操作</span><span>资源</span><span>操作者</span></div>{data.audit.map((item) => <div className="table-row" key={item.id}><span>{formatDate(item.created_at)}</span><b>{item.action}</b><span>{item.resource_type} / {item.resource_id?.slice(0, 8)}</span><span>{item.user_id?.slice(0, 8) || "系统"}</span></div>)}</div>{!data.audit.length && <Empty text="暂无审计记录。"/>}</Panel></div>; }

function ConsoleApp() {
  const [loggedIn, setLoggedIn] = useState(Boolean(localStorage.getItem("eai_session"))); const [me, setMe] = useState(null); const [page, setPage] = useState("overview"); const [data, setData] = useState({ projects: [], agents: [], workflows: [], applications: [], models: [], kbs: [], skills: [], plugins: [], mcp: [], runs: [], audit: [] });
  async function refresh() { try { const responses = await Promise.all(["/api/me", "/api/projects", "/api/agents", "/api/applications", "/api/workflows", "/api/models", "/api/knowledge-bases", "/api/skills", "/api/plugins", "/api/mcp-servers", "/api/runs", "/api/audit"].map((path) => api.get(path))); const [meR, projects, agents, applications, workflows, models, kbs, skills, plugins, mcp, runs, audit] = responses; setMe(meR.data); setData({ projects: projects.data, agents: agents.data, applications: applications.data, workflows: workflows.data, models: models.data, kbs: kbs.data, skills: skills.data, plugins: plugins.data, mcp: mcp.data, runs: runs.data, audit: audit.data }); } catch (err) { if (err.response?.status === 401) { localStorage.removeItem("eai_session"); setLoggedIn(false); } } }
  useEffect(() => { const params = new URLSearchParams(window.location.search); if (window.location.pathname === "/auth/oidc/callback" && params.get("code") && params.get("state")) { api.post("/api/auth/oidc/callback", { code: params.get("code"), state: params.get("state") }, { headers: { "X-Browser-Session": "1" } }).then(() => { localStorage.setItem("eai_session", "1"); window.history.replaceState({}, "", "/"); setLoggedIn(true); }).catch(() => { window.history.replaceState({}, "", "/"); }); } }, []);
  useEffect(() => { if (loggedIn) refresh(); }, [loggedIn]);
  if (!loggedIn) return window.location.pathname === "/reset-password" ? <PasswordReset /> : window.location.pathname === "/verify-email" ? <EmailVerification /> : <Login onLogin={() => setLoggedIn(true)}/>;
  const content = page === "overview" ? <Overview data={data} go={setPage}/> : page === "workspaces" ? <WorkspaceCenter me={me}/> : page === "agents" ? <Agents data={data} refresh={refresh}/> : page === "agent-studio" ? <AgentStudio data={data}/> : page === "agent-resources" ? <AgentResources data={data}/> : page === "agent-lifecycle" ? <AgentLifecycle data={data}/> : page === "applications" ? <ApplicationsCenter api={api} data={data} refresh={refresh}/> : page === "workflows" ? <Workflows data={data} refresh={refresh}/> : page === "workflow-ops" ? <WorkflowGovernance data={data}/> : page === "models" ? <Models data={data} refresh={refresh}/> : page === "model-experience" ? <ModelExperience api={api} data={data}/> : page === "model-square" ? <ModelSquare data={data}/> : page === "model-detail" ? <ModelDetail data={data}/> : page === "knowledge" ? <Knowledge data={data} refresh={refresh}/> : page === "kb-assets" ? <KnowledgeAssets data={data}/> : page === "databases" ? <><DatabaseCenter data={data}/><div className="page"><DatabasePolicyEditor api={api} role={me?.role}/></div></> : page === "prompts" ? <PromptCenter/> : page === "quick-chat" ? <QuickChat data={data}/> : page === "extensions" ? <ExtensionsControl data={data} refresh={refresh}/> : page === "explore" ? <MarketCenter/> : page === "runs" ? <RunsCenter api={api}/> : page === "members" ? <Members me={me}/> : page === "publishing" ? <PublishingCenter data={data}/> : page === "approvals" ? <ApprovalCenter/> : page === "production-governance" ? <ProductionGovernance api={api} role={me?.role}/> : page === "security" ? <SecurityCenter me={me}/> : page === "admin" ? <PlatformConsole/> : page === "platform-resources" ? <AdminResources/> : page === "account" ? <AccountCenter me={me}/> : <Audit data={data}/>;
  return <Layout me={me} page={page} setPage={setPage} onLogout={() => { api.post("/api/auth/logout", {}).catch(() => {}).finally(() => { localStorage.removeItem("eai_session"); setLoggedIn(false); }); }}>{content}</Layout>;
}

function App() {
  const match = window.location.pathname.match(/^\/apps\/([^/]+)\/([^/]+)$/);
  if (match) return <PublicApplication tenantSlug={decodeURIComponent(match[1])} appSlug={decodeURIComponent(match[2])}/>;
  return <ConsoleApp/>;
}

createRoot(document.getElementById("root")).render(<App/>);

