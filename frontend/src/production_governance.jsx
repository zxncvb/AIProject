import React, { useEffect, useState } from "react";

const label = { queued: "排队中", enqueued: "已入队", publishing: "投递中", delivering: "投递中", delivered: "已送达", failed: "失败", dead: "停止重试", pending: "待审批", approved: "已批准", rejected: "已拒绝" };
const errorText = (error) => typeof error?.response?.data?.detail === "string" ? error.response.data.detail : "操作失败";

export default function ProductionGovernance({ api, role }) {
  const [summary, setSummary] = useState(null);
  const [dead, setDead] = useState([]);
  const [deliveries, setDeliveries] = useState([]);
  const [policies, setPolicies] = useState([]);
  const [notice, setNotice] = useState("");
  const [form, setForm] = useState({ name: "生产发布双人审批", request_type: "channel.publish", resource_type: "", approver_roles: ["owner", "admin"], min_approvals: 2, allow_self_approval: false, expires_in_minutes: 1440, enabled: true, conditions: {} });
  const authorized = ["owner", "admin"].includes(role);

  async function load() {
    if (!authorized) return;
    try {
      const [queue, deadJobs, deliveryRows, policyRows] = await Promise.all([api.get("/api/admin/jobs/summary"), api.get("/api/admin/jobs/dead"), api.get("/api/publish/deliveries"), api.get("/api/approval-policies")]);
      setSummary(queue.data); setDead(deadJobs.data); setDeliveries(deliveryRows.data); setPolicies(policyRows.data); setNotice("");
    } catch (error) { setNotice(errorText(error)); }
  }
  useEffect(() => { load(); }, [authorized]);
  async function retryJob(id) { try { await api.post(`/api/admin/jobs/dead/${encodeURIComponent(id)}/retry`); setNotice("死信任务已重新入队"); await load(); } catch (error) { setNotice(errorText(error)); } }
  async function retryDelivery(id) { try { await api.post(`/api/publish/deliveries/${id}/retry`); setNotice("发布投递已重新入队"); await load(); } catch (error) { setNotice(errorText(error)); } }
  async function createPolicy(event) { event.preventDefault(); try { await api.post("/api/approval-policies", form); setNotice("审批策略已创建"); await load(); } catch (error) { setNotice(errorText(error)); } }
  async function removePolicy(id) { if (!window.confirm("确认删除该审批策略吗？")) return; try { await api.delete(`/api/approval-policies/${id}`); await load(); } catch (error) { setNotice(errorText(error)); } }
  if (!authorized) return <div className="page"><div className="empty">只有租户管理员可以查看生产治理中心。</div></div>;
  return <div className="page"><div className="page-title"><div><h1>生产治理中心</h1><p>集中管理可靠队列、死信恢复、发布投递和企业审批策略。</p></div><div className="page-actions"><button onClick={load}>刷新状态</button></div></div>
    <div className="stat-grid"><div className="stat blue"><span>队列消息</span><strong>{summary?.queued ?? "—"}</strong><small>{summary?.stream || "Redis Stream"}</small></div><div className="stat purple"><span>处理中</span><strong>{summary?.pending ?? "—"}</strong><small>{summary?.consumer_group || "消费者组"}</small></div><div className="stat"><span>死信任务</span><strong>{summary?.dead ?? "—"}</strong><small>可人工检查并重试</small></div><div className="stat green"><span>最大重试</span><strong>{summary?.max_attempts ?? "—"}</strong><small>超过后进入死信流</small></div></div>
    <div className="two-col"><section className="panel"><div className="panel-head"><div><h3>死信任务</h3><small>保留错误、尝试次数和原始资源 ID</small></div></div><div className="table compact-table">{dead.map((item) => <div className="table-row" key={item.message_id}><b>{item.kind}</b><span>{item.resource_id}</span><span>{item.last_error || "未知错误"}</span><button onClick={() => retryJob(item.message_id)}>重新入队</button></div>)}</div>{!dead.length && <div className="empty">当前没有死信任务</div>}</section>
      <section className="panel"><div className="panel-head"><div><h3>发布投递</h3><small>渠道回调采用持久化记录和签名请求</small></div></div><div className="table compact-table">{deliveries.map((item) => <div className="table-row" key={item.id}><b>{label[item.status] || item.status}</b><span>尝试 {item.attempt_count} 次</span><span>{item.error || item.delivered_at || "等待处理"}</span>{["failed", "dead"].includes(item.status) ? <button onClick={() => retryDelivery(item.id)}>重试</button> : <span>—</span>}</div>)}</div>{!deliveries.length && <div className="empty">暂无发布投递记录</div>}</section></div>
    <div className="two-col"><section className="panel"><div className="panel-head"><div><h3>审批策略</h3><small>支持角色范围、禁止自审和多人会签</small></div></div><div className="table compact-table">{policies.map((item) => <div className="table-row" key={item.id}><b>{item.name}</b><span>{item.request_type}</span><span>{item.min_approvals} 人批准</span><button onClick={() => removePolicy(item.id)}>删除</button></div>)}</div>{!policies.length && <div className="empty">尚未配置审批策略</div>}</section>
      <section className="panel"><div className="panel-head"><div><h3>新建审批策略</h3><small>策略会自动应用到同类型的新审批单</small></div></div><form className="form-grid" onSubmit={createPolicy}><label>策略名称<input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} required/></label><label>申请类型<select value={form.request_type} onChange={(event) => setForm({ ...form, request_type: event.target.value })}><option value="channel.publish">渠道发布</option><option value="database.query">数据库查询</option><option value="workflow.node">工作流人工节点</option><option value="resource.publish">资源发布</option></select></label><label>至少批准人数<input type="number" min="1" max="20" value={form.min_approvals} onChange={(event) => setForm({ ...form, min_approvals: Number(event.target.value) })}/></label><label><input type="checkbox" checked={form.allow_self_approval} onChange={(event) => setForm({ ...form, allow_self_approval: event.target.checked })}/> 允许申请人自审</label><button className="primary">创建策略</button></form></section></div>
    {notice && <div className="notice">{notice}</div>}
  </div>;
}
