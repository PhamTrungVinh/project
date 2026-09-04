import { useState, useRef, useEffect } from "react";
import { chatApi } from "../api.js";

export default function ChatView() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [threadId, setThreadId] = useState(null);
  const [route, setRoute] = useState("");
  const [sending, setSending] = useState(false);
  const logRef = useRef(null);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [messages]);

  function newChat() {
    setThreadId(null);
    setRoute("");
    setMessages([{ role: "system", text: "Đã bắt đầu cuộc trò chuyện mới" }]);
  }

  async function send() {
    const text = input.trim();
    if (!text || sending) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text }]);
    setSending(true);
    try {
      const data = await chatApi.send(text, threadId);
      setThreadId(data.thread_id);
      setRoute(data.route || "");
      setMessages((m) => [...m, { role: "assistant", text: data.answer }]);
    } catch (e) {
      setMessages((m) => [...m, { role: "system", text: "❌ Lỗi: " + e.message }]);
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="chat-view">
      <div className="view-header">
        <h3>Chat</h3>
        <button className="secondary" onClick={newChat}>
          ➕ New Chat
        </button>
      </div>
      <div className="thread-label">
        {threadId ? `Thread: ${threadId}` : "Thread: (chưa có)"}
        {route && `  •  route: ${route}`}
      </div>
      <div id="chat-log" ref={logRef}>
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            {m.text}
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
          disabled={sending}
        />
        <button onClick={send} disabled={sending}>
          {sending ? "..." : "Gửi"}
        </button>
      </div>
    </div>
  );
}