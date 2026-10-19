import React, { useEffect, useState } from "react";

function errorText(error) {
  const detail = error?.response?.data?.detail;
  return typeof detail === "string" ? detail : detail?.message || "操作失败，请稍后重试";
}

export default function ModelExperience({ api, data }) {
  const [catalog, setCatalog] = useState([]);
  const [conversations, setConversations] = useState([]);
  const [conversationId, setConversationId] = useState("");
  const [providerId, setProviderId] = useState("");
  const [knowledgeBaseId, setKnowledgeBaseId] = useState("");
  const [messages, setMessages] = useState([]);
  const [text, setText] = useState("");
  const [attachments, setAttachments] = useState([]);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  async function loadConversations() {
    const response = await api.get("/api/model-experience/conversations");
    setConversations(response.data);
  }

  useEffect(() => {
    Promise.all([api.get("/api/model-catalog"), api.get("/api/model-experience/conversations")])
      .then(([models, history]) => {
        setCatalog(models.data.filter((item) => item.enabled));
        setProviderId(models.data.find((item) => item.enabled)?.id || "");
        setConversations(history.data);
      })
      .catch((error) => setNotice(errorText(error)));
  }, []);

  async function openConversation(id) {
    try {
      const response = await api.get(`/api/model-experience/conversations/${id}`);
      setConversationId(id);
      setProviderId(response.data.provider_id);
      setMessages(response.data.messages || []);
      setAttachments([]);
      setNotice("");
    } catch (error) { setNotice(errorText(error)); }
  }

  function newConversation() {
    setConversationId("");
    setMessages([]);
    setText("");
    setAttachments([]);
    setNotice("");
  }

  async function deleteConversation() {
    if (!conversationId || !window.confirm("确认删除当前会话及其消息吗？")) return;
    try {
      await api.delete(`/api/model-experience/conversations/${conversationId}`);
      newConversation();
      await loadConversations();
    } catch (error) { setNotice(errorText(error)); }
  }

  async function addAttachments(event) {
    const files = Array.from(event.target.files || []);
    if (files.length + attachments.length > 3) { setNotice("最多添加 3 个文本附件"); return; }
    try {
      const loaded = await Promise.all(files.map(async (file) => {
        if (file.size > 16 * 1024) throw new Error(`${file.name} 超过 16 KiB`);
        if (!file.type.startsWith("text/") && !/\.(txt|md|csv|json|log)$/i.test(file.name)) throw new Error(`${file.name} 不是支持的文本文件`);
        return { name: file.name, content: await file.text() };
      }));
      setAttachments((current) => [...current, ...loaded]);
      setNotice("");
    } catch (error) { setNotice(error.message); }
    event.target.value = "";
  }

  async function send(event) {
    event.preventDefault();
    const question = text.trim();
    if (!question || !providerId || busy) return;
    setBusy(true);
    setNotice("");
    try {
      const response = await api.post("/api/model-experience/chat", {
        provider_id: providerId,
        conversation_id: conversationId || null,
        knowledge_base_id: knowledgeBaseId || null,
        attachments: attachments.map((item) => item.content),
        message: question,
      });
      setConversationId(response.data.conversation_id);
      setMessages((current) => [...current, { role: "user", content: question }, { role: "assistant", content: response.data.text, usage: response.data.usage, citations: response.data.citations }]);
      setText("");
      setAttachments([]);
      await loadConversations();
    } catch (error) { setNotice(errorText(error)); }
    finally { setBusy(false); }
  }

  return <div className="page">
    <div className="page-title"><div><h1>模型体验</h1><p>持久化对话、文本附件与知识库检索，调用实际接入的模型。</p></div><div className="page-actions"><button onClick={newConversation}>新建会话</button><button disabled={!conversationId} onClick={deleteConversation}>删除当前会话</button></div></div>
    <div className="experience-layout">
      <section className="panel"><div className="panel-head"><div><h3>会话历史</h3><small>仅显示当前账号的会话</small></div></div>
        <button className={`history-item ${!conversationId ? "active" : ""}`} onClick={newConversation}>＋ 新建对话</button>
        {conversations.map((item) => <button className={`history-item ${conversationId === item.id ? "active" : ""}`} key={item.id} onClick={() => openConversation(item.id)}><b>{item.title}</b><small>{item.message_count} 条消息 · {new Date(item.updated_at).toLocaleString("zh-CN")}</small></button>)}
        {!conversations.length && <div className="empty">暂无历史会话</div>}
      </section>
      <section className="panel"><div className="panel-head"><div><h3>大语言模型体验</h3><small>模型可在新会话中切换</small></div></div>
        <div className="experience-bar"><label>模型 <select value={providerId} disabled={Boolean(conversationId)} onChange={(event) => setProviderId(event.target.value)}><option value="">请选择模型</option>{catalog.map((item) => <option key={item.id} value={item.id}>{item.provider} / {item.name}</option>)}</select></label><label>知识检索 <select value={knowledgeBaseId} onChange={(event) => setKnowledgeBaseId(event.target.value)}><option value="">不使用知识库</option>{(data.kbs || []).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label className="file-button">文本附件<input type="file" multiple accept=".txt,.md,.csv,.json,.log,text/*" onChange={addAttachments}/></label></div>
        {attachments.length > 0 && <div className="notice">已选择：{attachments.map((item) => item.name).join("、")}（仅本次提问使用）</div>}
        <div className="chat-thread">{messages.map((item, index) => <div className={`chat-message ${item.role}`} key={`${index}-${item.role}`}><b>{item.role === "user" ? "我" : "模型"}</b><p>{item.content}</p>{item.usage && <small>Token：{item.usage.total_tokens || 0}</small>}{item.citations?.length > 0 && <details><summary>引用的知识片段（{item.citations.length}）</summary>{item.citations.map((citation, citationIndex) => <p key={citation.chunk_id || citationIndex}>[{citationIndex + 1}] {citation.content}</p>)}</details>}</div>)}{!messages.length && <div className="chat-placeholder">选择模型后输入问题，开始新的会话。</div>}</div>
        <form className="chat-compose" onSubmit={send}><textarea value={text} onChange={(event) => setText(event.target.value)} placeholder="输入你的问题…"/><button className="primary" disabled={busy || !providerId || !text.trim()}>{busy ? "生成中…" : "发送"}</button></form>
        {notice && <div className="notice">{notice}</div>}
      </section>
    </div>
  </div>;
}
