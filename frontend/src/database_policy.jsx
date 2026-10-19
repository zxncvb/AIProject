import React, { useEffect, useState } from "react";

const roles = ["owner", "admin", "developer", "editor", "operator", "viewer"];
const roleNames = { owner: "所有者", admin: "管理员", developer: "开发者", editor: "编辑者", operator: "运营者", viewer: "查看者" };

export default function DatabasePolicyEditor({ api, role }) {
  const [databases, setDatabases] = useState([]);
  const [databaseId, setDatabaseId] = useState("");
  const [columns, setColumns] = useState({});
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
        setNotice("");
      }).catch((error) => setNotice(typeof error?.response?.data?.detail === "string" ? error.response.data.detail : "字段策略读取失败"));
  }, [databaseId]);
  if (!authorized) return null;
  function change(name, patch) { setColumns((current) => ({ ...current, [name]: { allowed_roles: current[name]?.allowed_roles || [], mask: Boolean(current[name]?.mask), ...patch } })); }
  async function save() {
    try {
      await api.put(`/api/databases/${databaseId}/policy`, { columns });
      setNotice("字段策略已保存；查询结果将按角色过滤并脱敏");
    } catch (error) { setNotice(typeof error?.response?.data?.detail === "string" ? error.response.data.detail : "保存失败"); }
  }
  return <section className="panel" style={{ marginTop: 16 }}><div className="panel-head"><div><h3>数据库字段权限</h3><small>仅租户管理员可配置；空角色列表表示所有角色可见</small></div><button className="primary" disabled={!databaseId} onClick={save}>保存策略</button></div>
    <label>数据库 <select value={databaseId} onChange={(event) => setDatabaseId(event.target.value)}><option value="">选择数据库</option>{databases.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
    <div className="table policy-table"><div className="table-head"><span>字段</span><span>可见角色</span><span>结果脱敏</span></div>{available.map((name) => <div className="table-row" key={name}><b>{name}</b><div className="button-row">{roles.map((item) => <label key={item} title={roleNames[item]}><input type="checkbox" checked={(columns[name]?.allowed_roles || []).includes(item)} onChange={(event) => change(name, { allowed_roles: event.target.checked ? [...(columns[name]?.allowed_roles || []), item] : (columns[name]?.allowed_roles || []).filter((value) => value !== item) })}/>{roleNames[item]}</label>)}</div><label><input type="checkbox" checked={Boolean(columns[name]?.mask)} onChange={(event) => change(name, { mask: event.target.checked })}/> 脱敏</label></div>)}</div>
    {!available.length && <div className="empty">请先同步数据库表结构</div>}{notice && <div className="notice">{notice}</div>}
  </section>;
}
