import React, { useEffect, useMemo, useState } from "react";

const statusLabels = { draft: "草稿", deployed: "已部署", archived: "已归档", queued: "排队中", building: "构建中", succeeded: "成功", failed: "失败", deploying: "部署中", active: "运行中", stopping: "下线中", stopped: "已下线", superseded: "已替换" };
const messageOf = (error) => typeof error?.response?.data?.detail === "string" ? error.response.data.detail : "操作失败，请检查输入或权限";

export default function ApplicationsCenter({ api, data, refresh }) {
  const [kind, setKind] = useState("all");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [detail, setDetail] = useState(null);
  const [builds, setBuilds] = useState([]);
  const [deployments, setDeployments] = useState([]);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ name: "", slug: "", app_type: "low_code", description: "", runtime: "{}", source: "{}" });
  const visible = useMemo(() => data.applications.filter((item) => (kind === "all" || item.app_type === kind) && (!query || `${item.name} ${item.slug} ${item.description || ""}`.toLowerCase().includes(query.toLowerCase()))), [data.applications, kind, query]);

  async function loadDetail(id) {
    try {
      const application = (await api.get(`/api/applications/${id}`)).data;
      setDetail(application);
      setSelectedId(id);
      if (application.app_type === "full_code") {
        const [buildHistory, deploymentHistory] = await Promise.all([api.get(`/api/applications/${id}/builds`), api.get(`/api/applications/${id}/deployments`)]);
        setBuilds(buildHistory.data);
        setDeployments(deploymentHistory.data);
      } else { setBuilds([]); setDeployments([]); }
    } catch (error) { setNotice(messageOf(error)); }
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
  async function deployVersion(id) {
    try { const result = await api.post(`/api/applications/${id}/deploy`); setNotice(`版本 v${result.data.version} 已发布`); await refresh(); await loadDetail(id); }
    catch (error) { setNotice(messageOf(error)); }
  }
  async function buildImage(id) {
    setBusy(true);
    try { const result = await api.post(`/api/applications/${id}/builds`, {}); setNotice(`镜像构建已入队：${result.data.image}`); await loadDetail(id); }
    catch (error) { setNotice(messageOf(error)); }
    finally { setBusy(false); }
  }
  async function hostLatestBuild() {
    const build = builds.find((item) => item.status === "succeeded");
    if (!build) { setNotice("还没有成功的镜像构建"); return; }
    setBusy(true);
    try { const result = await api.post(`/api/applications/${selectedId}/deployments`, { build_id: build.id, environment: "production", replicas: 1, container_port: 8080, health_path: "/healthz", env: {}, secret_refs: {} }); setNotice(`托管部署 r${result.data.revision} 已提交`); await loadDetail(selectedId); }
    catch (error) { setNotice(messageOf(error)); }
    finally { setBusy(false); }
  }
  async function stopDeployment(id) {
    if (!window.confirm("确认下线该托管部署吗？")) return;
    try { await api.delete(`/api/application-deployments/${id}`); setNotice("下线任务已提交"); await loadDetail(selectedId); }
    catch (error) { setNotice(messageOf(error)); }
  }
  async function rollback(version) {
    if (!window.confirm(`确认回滚至 v${version} 吗？`)) return;
    try { await api.post(`/api/applications/${selectedId}/rollback`, { version }); setNotice(`已回滚至 v${version}`); await refresh(); await loadDetail(selectedId); }
    catch (error) { setNotice(messageOf(error)); }
  }
  async function rollbackDeployment(id) {
    if (!window.confirm("确认将线上工作负载回滚到这个部署吗？")) return;
    try { const result = await api.post(`/api/application-deployments/${id}/rollback`); setNotice(`回滚部署 r${result.data.revision} 已提交`); await loadDetail(selectedId); }
    catch (error) { setNotice(messageOf(error)); }
  }

  return <div className="page"><div className="page-title"><div><h1>应用中心</h1><p>管理低代码应用以及全代码镜像构建、在线托管、滚动发布与回滚。</p></div><div className="page-actions"><button className="primary" onClick={() => document.getElementById("app-form")?.scrollIntoView({ behavior: "smooth" })}>＋ 创建应用</button></div></div>
    <div className="sub-tabs"><button className={kind === "all" ? "active" : ""} onClick={() => setKind("all")}>全部应用</button><button className={kind === "low_code" ? "active" : ""} onClick={() => setKind("low_code")}>低代码</button><button className={kind === "full_code" ? "active" : ""} onClick={() => setKind("full_code")}>全代码</button><div className="table-tools"><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索名称、标识或描述"/></div></div>
    <div className="app-grid">{visible.map((item) => <article className="app-card" key={item.id}><div className="app-card-top"><div className="asset-icon app-icon">{item.app_type === "low_code" ? "▦" : "{ }"}</div><span className="tag green">{statusLabels[item.status] || item.status}</span></div><h3>{item.name}</h3><p>{item.description || "暂无描述"}</p><small>{item.app_type === "low_code" ? "低代码" : "全代码"} · {item.slug}</small><div className="card-actions"><button onClick={() => loadDetail(item.id)}>详情</button><button onClick={() => deployVersion(item.id)}>发布版本</button>{item.app_type === "full_code" && <button disabled={busy} onClick={() => buildImage(item.id)}>构建镜像</button>}</div></article>)}{!visible.length && <div className="empty">没有符合条件的应用</div>}</div>
    <div className="two-col app-bottom"><section className="panel"><div className="panel-head"><div><h3>创建应用</h3><small>全代码源码使用 HTTPS Git 仓库，由集群 BuildKit 构建</small></div></div><form id="app-form" className="form-grid" onSubmit={create}><label>名称<input required value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })}/></label><label>唯一标识<input required value={form.slug} onChange={(event) => setForm({ ...form, slug: event.target.value })}/></label><label>类型<select value={form.app_type} onChange={(event) => setForm({ ...form, app_type: event.target.value })}><option value="low_code">低代码</option><option value="full_code">全代码</option></select></label><label>描述<textarea value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })}/></label><label>运行时清单 JSON<textarea value={form.runtime} onChange={(event) => setForm({ ...form, runtime: event.target.value })}/></label><label>应用源码/配置 JSON<textarea value={form.source} onChange={(event) => setForm({ ...form, source: event.target.value })}/></label>{form.app_type === "full_code" && <small>源码示例：{`{"git_url":"https://git.example.com/team/app.git","git_ref":"main","dockerfile":"Dockerfile","context":"."}`}</small>}<button className="primary">保存草稿</button></form></section>
      {detail && <section className="panel"><div className="panel-head"><div><h3>应用详情</h3><small>{detail.name}</small></div><button onClick={() => { setDetail(null); setSelectedId(""); }}>关闭</button></div><p>{detail.description || "暂无描述"}</p><h4>版本历史</h4><div className="table compact-table">{detail.versions.map((version) => <div className="table-row" key={version.id}><b>v{version.version}</b><span>{statusLabels[version.status] || version.status}</span><span>{new Date(version.created_at).toLocaleString("zh-CN")}</span><button disabled={version.status === "deployed"} onClick={() => rollback(version.version)}>回滚至此版本</button></div>)}</div>{detail.app_type === "full_code" && <><div className="panel-head compact"><div><h4>镜像构建</h4><small>BuildKit 根less 构建并推送企业镜像仓库</small></div><button disabled={busy} onClick={() => buildImage(detail.id)}>新建构建</button></div><div className="table compact-table">{builds.map((item) => <div className="table-row" key={item.id}><b>v{item.version}</b><span>{statusLabels[item.status] || item.status}</span><span title={item.image}>{item.image.slice(0, 28)}</span><button onClick={() => loadDetail(selectedId)}>刷新</button></div>)}</div><div className="panel-head compact"><div><h4>在线托管</h4><small>滚动部署、健康检查和版本回滚</small></div><button disabled={busy || !builds.some((item) => item.status === "succeeded")} onClick={hostLatestBuild}>部署最新镜像</button></div><div className="table compact-table">{deployments.map((item) => <div className="table-row" key={item.id}><b>r{item.revision} / v{item.version}</b><span>{statusLabels[item.status] || item.status}</span><span>{item.endpoint_url || item.image.slice(0, 24)}</span><span className="button-row"><button onClick={() => rollbackDeployment(item.id)}>回滚到此处</button>{["queued", "deploying", "active"].includes(item.status) && <button onClick={() => stopDeployment(item.id)}>下线</button>}</span></div>)}</div></>}<details><summary>运行时清单</summary><pre className="json-view">{JSON.stringify(detail.runtime, null, 2)}</pre></details></section>}
    </div>{notice && <div className="notice">{notice}</div>}
  </div>;
}
