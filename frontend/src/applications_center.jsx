import React, { useEffect, useMemo, useState } from "react";

const statusLabels = { draft: "草稿", deployed: "已部署", archived: "已归档" };
const messageOf = (error) => typeof error?.response?.data?.detail === "string" ? error.response.data.detail : "操作失败，请检查输入或权限";

export default function ApplicationsCenter({ api, data, refresh }) {
  const [kind, setKind] = useState("all");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [detail, setDetail] = useState(null);
  const [notice, setNotice] = useState("");
  const [form, setForm] = useState({ name: "", slug: "", app_type: "low_code", description: "", runtime: "{}", source: "{}" });
  const visible = useMemo(() => data.applications.filter((item) => (kind === "all" || item.app_type === kind) && (!query || `${item.name} ${item.slug} ${item.description || ""}`.toLowerCase().includes(query.toLowerCase()))), [data.applications, kind, query]);
  async function loadDetail(id) {
    try { setDetail((await api.get(`/api/applications/${id}`)).data); setSelectedId(id); setNotice(""); }
    catch (error) { setNotice(messageOf(error)); }
  }
  useEffect(() => { if (selectedId) loadDetail(selectedId); }, [data.applications]);
  async function create(event) {
    event.preventDefault();
    try {
      const projectId = data.projects[0]?.id;
      if (!projectId) { setNotice("请先创建项目，再创建应用"); return; }
      const response = await api.post("/api/applications", { ...form, project_id: projectId, runtime: JSON.parse(form.runtime), source: JSON.parse(form.source) });
      setNotice("应用草稿已创建；请检查版本配置后手动部署");
      setForm({ ...form, name: "", slug: "" });
      await refresh(); await loadDetail(response.data.id);
    } catch (error) { setNotice(error instanceof SyntaxError ? "运行时或源码不是有效 JSON" : messageOf(error)); }
  }
  async function deploy(id) {
    try { const result = await api.post(`/api/applications/${id}/deploy`); setNotice(`版本 v${result.data.version} 已部署`); await refresh(); await loadDetail(id); }
    catch (error) { setNotice(messageOf(error)); }
  }
  async function rollback(version) {
    if (!window.confirm(`确认回滚至 v${version} 吗？`)) return;
    try { await api.post(`/api/applications/${selectedId}/rollback`, { version }); setNotice(`已回滚至 v${version}`); await refresh(); await loadDetail(selectedId); }
    catch (error) { setNotice(messageOf(error)); }
  }

  return <div className="page"><div className="page-title"><div><h1>应用中心</h1><p>管理低代码和全代码应用的草稿、版本、部署与回滚。</p></div><div className="page-actions"><button className="primary" onClick={() => document.getElementById("app-form")?.scrollIntoView({ behavior: "smooth" })}>＋ 创建应用</button></div></div>
    <div className="sub-tabs"><button className={kind === "all" ? "active" : ""} onClick={() => setKind("all")}>全部应用</button><button className={kind === "low_code" ? "active" : ""} onClick={() => setKind("low_code")}>低代码</button><button className={kind === "full_code" ? "active" : ""} onClick={() => setKind("full_code")}>全代码</button><div className="table-tools"><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索名称、标识或描述"/></div></div>
    <div className="app-grid">{visible.map((item) => <article className="app-card" key={item.id}><div className="app-card-top"><div className="asset-icon app-icon">{item.app_type === "low_code" ? "▦" : "{ }"}</div><span className="tag green">{statusLabels[item.status] || item.status}</span></div><h3>{item.name}</h3><p>{item.description || "暂无描述"}</p><small>{item.app_type === "low_code" ? "低代码" : "全代码"} · {item.slug}</small><div className="card-actions"><button onClick={() => loadDetail(item.id)}>详情</button><button onClick={() => deploy(item.id)}>部署最新版本</button></div></article>)}{!visible.length && <div className="empty">没有符合条件的应用</div>}</div>
    <div className="two-col app-bottom"><section className="panel"><div className="panel-head"><div><h3>创建应用</h3><small>创建草稿后可检查并部署</small></div></div><form id="app-form" className="form-grid" onSubmit={create}><label>名称<input required value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })}/></label><label>唯一标识<input required value={form.slug} onChange={(event) => setForm({ ...form, slug: event.target.value })}/></label><label>类型<select value={form.app_type} onChange={(event) => setForm({ ...form, app_type: event.target.value })}><option value="low_code">低代码</option><option value="full_code">全代码</option></select></label><label>描述<textarea value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })}/></label><label>运行时清单 JSON<textarea value={form.runtime} onChange={(event) => setForm({ ...form, runtime: event.target.value })}/></label><label>应用源码/配置 JSON<textarea value={form.source} onChange={(event) => setForm({ ...form, source: event.target.value })}/></label>{form.app_type === "full_code" && <small>全代码应用需要 runtime、source.command、镜像和 Kubernetes 沙箱控制器；当前执行形态为批处理任务。</small>}<button className="primary">保存草稿</button></form></section>
      {detail && <section className="panel"><div className="panel-head"><div><h3>应用详情</h3><small>{detail.name}</small></div><button onClick={() => { setDetail(null); setSelectedId(""); }}>关闭</button></div><p>{detail.description || "暂无描述"}</p><h4>版本历史</h4><div className="table compact-table">{detail.versions.map((version) => <div className="table-row" key={version.id}><b>v{version.version}</b><span>{statusLabels[version.status] || version.status}</span><span>{new Date(version.created_at).toLocaleString("zh-CN")}</span><button disabled={version.status === "deployed"} onClick={() => rollback(version.version)}>回滚至此版本</button></div>)}</div><details><summary>运行时清单</summary><pre className="json-view">{JSON.stringify(detail.runtime, null, 2)}</pre></details></section>}
    </div>{notice && <div className="notice">{notice}</div>}
  </div>;
}
