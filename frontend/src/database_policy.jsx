import React, { useEffect, useState } from "react";

const roles = ["owner", "admin", "developer", "editor", "operator", "viewer"];
const roleNames = { owner: "所有者", admin: "管理员", developer: "开发者", editor: "编辑者", operator: "运营者", viewer: "查看者" };

export default function DatabasePolicyEditor({ api, role }) {
  const [databases, setDatabases] = useState([]);
  const [databaseId, setDatabaseId] = useState("");
  const [columns, setColumns] = useState({});
  const [governance, setGovernance] = useState({ require_approval: false, require_native_read_only: true, max_rows: 100, query_timeout_ms: 8000, security_posture: null });
  const [available, setAvailable] = useState([]);
  const [notice, setNotice] = useState("");
  const authorized = ["owner", "admin"].includes(role);
  useEffect(() => {
    if (!authorized) return;
    api.get("/api/databases").then((response) => { setDatabases(response.data); setDatabaseId(response.data[0]?.id || ""); }).catch(() => setNotice("数据库列表读取失败"));
  }, [authorized]);
  useEffect(() => {
    if (!databaseId) return;
    Promise.all([api.get(`/api/databases/${databaseId}`), api.get(`/api/databases/${databaseId}/policy`)])
      .then(([detail, policy]) => {
        setAvailable([...new Set((detail.data.tables || []).flatMap((table) => (table.columns || []).map((column) => column.name)))]);
        setColumns(policy.data.columns || {});
        setGovernance({ require_approval: Boolean(policy.data.require_approval), require_native_read_only: policy.data.require_native_read_only !== false, max_rows: policy.data.max_rows || 100, query_timeout_ms: policy.data.query_timeout_ms || 8000, security_posture: policy.data.security_posture || null });
        setNotice("");
      }).catch((error) => setNotice(typeof error?.response?.data?.detail === "string" ? error.response.data.detail : "字段策略读取失败"));
  }, [databaseId]);
  if (!authorized) return null;
  function change(name, patch) { setColumns((current) => ({ ...current, [name]: { allowed_roles: current[name]?.allowed_roles || [], mask: Boolean(current[name]?.mask), ...patch } })); }
  async function save() {
    try {
      await api.put(`/api/databases/${databaseId}/policy`, { columns, require_approval: governance.require_approval, require_native_read_only: governance.require_native_read_only, max_rows: governance.max_rows, query_timeout_ms: governance.query_timeout_ms });
      setNotice("数据库治理策略已保存");
    } catch (error) { setNotice(typeof error?.response?.data?.detail === "string" ? error.response.data.detail : "保存失败"); }
  }
  async function inspectSecurity() {
    try { const response = await api.post(`/api/databases/${databaseId}/security-posture`); setGovernance((current) => ({ ...current, security_posture: response.data })); setNotice(response.data.native_read_only ? "数据库账号原生只读检查通过" : "数据库账号仍拥有写权限，请更换最小权限账号"); }
    catch (error) { setNotice(typeof error?.response?.data?.detail === "string" ? error.response.data.detail : "安全检查失败"); }
  }
  return <section className="panel" style={{ marginTop: 16 }}><div className="panel-head"><div><h3>数据库访问治理</h3><small>审批、原生只读、查询上限、超时、字段可见性和脱敏统一配置</small></div><div className="button-row"><button disabled={!databaseId} onClick={inspectSecurity}>检查账号权限</button><button className="primary" disabled={!databaseId} onClick={save}>保存策略</button></div></div>
    <label>数据库 <select value={databaseId} onChange={(event) => setDatabaseId(event.target.value)}><option value="">选择数据库</option>{databases.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
    <div className="settings-grid" style={{ marginTop: 12 }}><label><input type="checkbox" checked={governance.require_approval} onChange={(event) => setGovernance({ ...governance, require_approval: event.target.checked })}/> 查询前必须审批</label><label><input type="checkbox" checked={governance.require_native_read_only} onChange={(event) => setGovernance({ ...governance, require_native_read_only: event.target.checked })}/> 强制数据库原生只读账号</label><label>最多返回行数<input type="number" min="1" max="1000" value={governance.max_rows} onChange={(event) => setGovernance({ ...governance, max_rows: Number(event.target.value) })}/></label><label>查询超时（毫秒）<input type="number" min="500" max="60000" value={governance.query_timeout_ms} onChange={(event) => setGovernance({ ...governance, query_timeout_ms: Number(event.target.value) })}/></label></div>
    {governance.security_posture && <div className="notice">原生只读：{governance.security_posture.native_read_only ? "已验证" : "未通过"} · 检查时间：{governance.security_posture.checked_at || "—"}</div>}
    <div className="table policy-table"><div className="table-head"><span>字段</span><span>可见角色</span><span>结果脱敏</span></div>{available.map((name) => <div className="table-row" key={name}><b>{name}</b><div className="button-row">{roles.map((item) => <label key={item} title={roleNames[item]}><input type="checkbox" checked={(columns[name]?.allowed_roles || []).includes(item)} onChange={(event) => change(name, { allowed_roles: event.target.checked ? [...(columns[name]?.allowed_roles || []), item] : (columns[name]?.allowed_roles || []).filter((value) => value !== item) })}/>{roleNames[item]}</label>)}</div><label><input type="checkbox" checked={Boolean(columns[name]?.mask)} onChange={(event) => change(name, { mask: event.target.checked })}/> 脱敏</label></div>)}</div>
    {!available.length && <div className="empty">请先同步数据库表结构</div>}{notice && <div className="notice">{notice}</div>}
  </section>;
}
