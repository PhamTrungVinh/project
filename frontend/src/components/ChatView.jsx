import { useState, useRef, useEffect } from "react";
import { chatApi } from "../api.js";
import AssistantMessage from "./AssistantMessage.js";

export default function ChatView({ initialThreadId = null, onThreadChange = () => {},
  onBusyChange = () => {}, onNewChat = () => {}, onTurnComplete = () => {}, disabled = false }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [threadId, setThreadId] = useState(initialThreadId);
  const [title, setTitle] = useState("Chat");
  const [loading, setLoading] = useState(Boolean(initialThreadId));
  const [loadError, setLoadError] = useState("");
  const [reload, setReload] = useState(0);
  const [route, setRoute] = useState("");
  const [sending, setSending] = useState(false);
  const logRef = useRef(null);
  const requestRef = useRef(null);
  // The parent remounts this view on explicit selection. Stream-start changes
  // only the active sidebar highlight and must not reload this view mid-turn.
  const initialThread = useRef(initialThreadId);

  useEffect(() => {
    const thread = initialThread.current;
    if (!thread) return;
    const controller = new AbortController();
    setLoading(true);
    setLoadError("");
    chatApi.history(thread, controller.signal).then((data) => {
      if (controller.signal.aborted) return;
      setMessages(data.messages);
      setTitle(data.title || "Untitled chat");
      setRoute(data.route || "");
      if (!data.history_available) {
        setMessages([{ role: "system", text: "Saved messages are unavailable for this chat. You can continue the conversation here." }]);
      }
    }).catch((error) => {
      if (!controller.signal.aborted) setLoadError(error.message);
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [reload]);

  useEffect(() => () => requestRef.current?.abort(), []);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [messages]);

  async function send() {
    const text = input.trim();
    if (!text || sending || loading || loadError || disabled) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text }]);
    setSending(true);
    onBusyChange(true);
    if (!threadId) setTitle(text.slice(0, 255));
    const controller = new AbortController();
    const replyId = crypto.randomUUID();
    function updateReply(text, append = false) {
      setMessages((messages) => {
        const reply = messages.find((message) => message.id === replyId);
        if (!reply) return [...messages, { id: replyId, role: "assistant", text }];
        return messages.map((message) => message.id === replyId
          ? { ...message, text: append ? message.text + text : text } : message);
      });
    }
    requestRef.current = controller;
    try {
      const data = await chatApi.stream(text, threadId, (event, payload) => {
        if (event === "start") {
          setThreadId(payload.thread_id);
          onThreadChange(payload.thread_id);
        }
        if (event === "delta") updateReply(payload.text, true);
      }, controller.signal);
      if (controller.signal.aborted) return;
      setThreadId(data.thread_id);
      onThreadChange(data.thread_id);
      setRoute(data.route || "");
      updateReply(data.answer);
    } catch (e) {
      if (!controller.signal.aborted) {
        setMessages((m) => [...m, { role: "system", text: "❌ Lỗi: " + e.message }]);
      }
    } finally {
      requestRef.current = null;
      setSending(false);
      onBusyChange(false);
      if (!controller.signal.aborted) onTurnComplete();
    }
  }

  return (
    <div className="chat-view">
      <div className="view-header">
        <h3 className="chat-title" title={title}>{title}</h3>
        <button className="secondary" onClick={onNewChat} disabled={sending || disabled}>
          ➕ New Chat
        </button>
      </div>
      <div className="thread-label">
        {threadId ? `Thread: ${threadId}` : "Thread: (chưa có)"}
        {route && `  •  route: ${route}`}
      </div>
      <div id="chat-log" ref={logRef}>
        {loading && <p role="status">Loading conversation…</p>}
        {loadError && <div className="error" role="alert">{loadError}
          <button className="secondary" onClick={() => setReload((value) => value + 1)}>Retry</button>
        </div>}
        {messages.map((m, i) => (
          <div key={m.id || i} className={`msg ${m.role}`}>
            {m.role === "assistant" ? <AssistantMessage text={m.text} /> : m.text}
          </div>
        ))}
      </div>
      <div className="chat-input-row">
        <input
          type="text"
          placeholder="Nhập tin nhắn..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          disabled={sending || loading || Boolean(loadError) || disabled}
        />
        <button onClick={send} disabled={sending || loading || Boolean(loadError) || disabled}>
          {sending ? "..." : "Gửi"}
        </button>
      </div>
    </div>
  );
}
