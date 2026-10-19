import React, { useEffect, useState } from "react";

const labels = { queued: "排队中", running: "运行中", waiting_approval: "等待审批", succeeded: "成功", failed: "失败", cancelled: "已取消" };
const messageOf = (error) => typeof error?.response?.data?.detail === "string" ? error.response.data.detail : "操作失败，请稍后重试";

export default function RunsCenter({ api }) {
  const [runs, setRuns] = useState([]);
  const [summary, setSummary] = useState(null);
  const [selected, setSelected] = useState(null);
  const [deadLetterOnly, setDeadLetterOnly] = useState(false);
  const [notice, setNotice] = useState("");

  async function load() {
    try {
      const [items, metrics] = await Promise.all([api.get(deadLetterOnly ? "/api/runs/dead-letter" : "/api/runs"), api.get("/api/observability/summary")]);
      setRuns(items.data);
      setSummary(metrics.data);
    } catch (error) { setNotice(messageOf(error)); }
  }
  useEffect(() => { load(); }, [deadLetterOnly]);

  async function detail(id) {
    try { setSelected((await api.get(`/api/runs/${id}`)).data); setNotice(""); }
    catch (error) { setNotice(messageOf(error)); }
  }
  async function action(id, kind) {
    if (kind === "cancel" && !window.confirm("确认取消该运行任务吗？")) return;
    try {
      const response = await api.post(`/api/runs/${id}/${kind}`);
      setNotice(kind === "retry" ? `已创建重试任务：${response.data.run_id}` : "任务已取消");
      if (kind === "cancel" && selected?.id === id) await detail(id);
      await load();
    } catch (error) { setNotice(messageOf(error)); }
  }
  function exportRuns() {
    const blob = new Blob([JSON.stringify(runs, null, 2)], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a"); link.href = url; link.download = "工作流运行记录.json"; link.click(); URL.revokeObjectURL(url);
  }

  return <div className="page"><div className="page-title"><div><h1>运行与观测</h1><p>查看执行链路、失败任务并进行重试或取消。</p></div><div className="page-actions"><button onClick={load}>刷新</button><button onClick={exportRuns}>导出当前列表</button></div></div>
    <div className="stat-grid"><div className="stat-card"><small>总运行数</small><b>{summary?.total_runs ?? "—"}</b></div><div className="stat-card"><small>近 30 天成功率</small><b>{summary ? `${(Number(summary.success_rate_30d || 0) * 100).toFixed(1)}%` : "—"}</b></div><div className="stat-card"><small>平均延迟</small><b>{summary ? `${summary.avg_latency_ms_30d || 0} ms` : "—"}</b></div><div className="stat-card"><small>Token 用量</small><b>{summary?.usage?.tokens ?? "—"}</b></div></div>
    <div className="sub-tabs"><button className={!deadLetterOnly ? "active" : ""} onClick={() => setDeadLetterOnly(false)}>全部运行</button><button className={deadLetterOnly ? "active" : ""} onClick={() => setDeadLetterOnly(true)}>失败任务</button></div>
    <section className="panel"><div className="panel-head"><h3>{deadLetterOnly ? "失败任务队列" : "最近运行记录"}</h3><small>最多显示 100 条</small></div><div className="table run-table"><div className="table-head"><span>运行 ID</span><span>工作流</span><span>状态</span><span>时间</span><span>操作</span></div>{runs.map((run) => <div className="table-row" key={run.id}><b title={run.id}>{run.id.slice(0, 12)}</b><span title={run.workflow_id}>{run.workflow_id?.slice(0, 12) || "—"}</span><span>{labels[run.status] || run.status || "失败"}</span><span>{new Date(run.created_at || run.finished_at).toLocaleString("zh-CN")}</span><div className="button-row"><button onClick={() => detail(run.id)}>详情</button>{["failed", "cancelled"].includes(run.status || "failed") && <button onClick={() => action(run.id, "retry")}>重试</button>}{["queued", "running", "waiting_approval"].includes(run.status) && <button onClick={() => action(run.id, "cancel")}>取消</button>}</div></div>)}</div>{!runs.length && <div className="empty">暂无运行记录</div>}</section>
    {selected && <section className="panel"><div className="panel-head"><div><h3>运行详情</h3><small>{selected.id} · {labels[selected.status] || selected.status}</small></div><button onClick={() => setSelected(null)}>关闭</button></div>{selected.retry_of_id && <p>重试来源：{selected.retry_of_id}</p>}{selected.error && <div className="notice">错误：{selected.error}</div>}<pre className="json-view">{JSON.stringify({ input: selected.input, state: selected.state, output: selected.output, trace_id: selected.trace_id }, null, 2)}</pre></section>}
    {notice && <div className="notice">{notice}</div>}
  </div>;
}
