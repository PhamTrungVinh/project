import { useState, useEffect, useRef } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import LoginPage from "./components/LoginPage.jsx";
import RegisterPage from "./components/RegisterPage.jsx";
import ChatView from "./components/ChatView.jsx";
import TicketsView from "./components/TicketsView.jsx";
import BookingsView from "./components/BookingsView.jsx";
import MemoryView from "./components/MemoryView.jsx";
import { authApi, chatApi, getToken, setToken } from "./api.js";

const TABS = [
  { id: "chat", label: "💬 Chat" },
  { id: "tickets", label: "🎫 Tickets" },
  { id: "bookings", label: "📅 Bookings" },
  { id: "memory", label: "🧠 Memory" },
];

function ChatCreatedAt({ value }) {
  if (!value) return null;
  // Legacy SQLite timestamps have no offset, but are stored in UTC.
  const timestamp = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : value + "Z";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return null;
  const day = date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  const time = date.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
  return <time className="conversation-created" dateTime={date.toISOString()} title={date.toLocaleString()}>
    {day} · {time}
  </time>;
}

function MainApp({ user, onLogout }) {
  const [tab, setTab] = useState("chat");
  const [conversations, setConversations] = useState([]);
  const [activeThreadId, setActiveThreadId] = useState(null);
  const [chatVersion, setChatVersion] = useState(0);
  const [chatBusy, setChatBusy] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState("");
  const [hasMore, setHasMore] = useState(false);
  const [deletingThread, setDeletingThread] = useState(null);
  const [deleteError, setDeleteError] = useState("");
  const navigationBusy = chatBusy || Boolean(deletingThread);
  const listRequest = useRef(0);

  async function loadConversations(skip = 0) {
    const version = ++listRequest.current;
    setHistoryLoading(true);
    setHistoryError("");
    try {
      const rows = await chatApi.listConversations(skip);
      if (version !== listRequest.current) return;
      setConversations((current) => skip === 0 ? rows
        : [...current, ...rows.filter((row) => !current.some((item) => item.thread_id === row.thread_id))]);
      setHasMore(rows.length === 50);
    } catch (error) {
      if (version === listRequest.current) setHistoryError(error.message);
    } finally {
      if (version === listRequest.current) setHistoryLoading(false);
    }
  }

  useEffect(() => {
    loadConversations();
    return () => { listRequest.current += 1; };
  }, []);

  function selectChat(threadId) {
    if (navigationBusy) return;
    setActiveThreadId(threadId);
    setChatVersion((version) => version + 1);
    setTab("chat");
  }

  async function deleteChat(conversation) {
    if (navigationBusy) return;
    if (!window.confirm(`Delete "${conversation.title || "Untitled chat"}"? This permanently removes its saved messages and pending approvals.`)) return;
    setDeletingThread(conversation.thread_id);
    setDeleteError("");
    // Prevent an earlier list request from reintroducing a deleted row.
    listRequest.current += 1;
    setHistoryLoading(false);
    try {
      await chatApi.deleteConversation(conversation.thread_id);
      setConversations((rows) => rows.filter((row) => row.thread_id !== conversation.thread_id));
      if (activeThreadId === conversation.thread_id) {
        setActiveThreadId(null);
        setChatVersion((version) => version + 1);
      }
      await loadConversations();
    } catch (error) {
      setDeleteError(error.message);
    } finally {
      setDeletingThread(null);
    }
  }

  return (
    <div id="app">
      <div id="sidebar">
        <div id="user-info">
          {user.full_name || user.email}
          <br />({user.email})
        </div>
        {TABS.map((t) => (
          <button
            key={t.id}
            className={"tab-btn" + (tab === t.id ? " active" : "")}
            onClick={() => setTab(t.id)}
            disabled={navigationBusy}
          >
            {t.label}
          </button>
        ))}
        <section className="conversation-history" aria-label="Previous chats">
          <div className="history-header">
            <h4>Previous chats</h4>
            <button className="secondary" onClick={() => selectChat(null)} disabled={navigationBusy}>
              ＋ New
            </button>
          </div>
          <div className="conversation-list">
            {conversations.map((conversation) => (
              <div className="conversation-row" key={conversation.thread_id}>
              <button
                className={"conversation-btn" + (activeThreadId === conversation.thread_id ? " active" : "")}
                aria-current={activeThreadId === conversation.thread_id ? "true" : undefined}
                title={conversation.title || "Untitled chat"}
                onClick={() => selectChat(conversation.thread_id)} disabled={navigationBusy}>
                <span className="conversation-title">{conversation.title || "Untitled chat"}</span>
                <ChatCreatedAt value={conversation.created_at} />
              </button>
              <button className="delete-chat" aria-label={`Delete chat: ${conversation.title || "Untitled chat"}`}
                title="Delete chat" onClick={() => deleteChat(conversation)} disabled={navigationBusy}>
                {deletingThread === conversation.thread_id ? "…" : "×"}
              </button>
              </div>
            ))}
            {deleteError && <p className="error" role="alert">{deleteError}</p>}
            {historyLoading && <p className="history-note" role="status">Loading chats…</p>}
            {!historyLoading && !historyError && conversations.length === 0 &&
              <p className="history-note">No previous chats yet.</p>}
            {historyError && <div className="error" role="alert">
              {historyError}
              <button className="secondary" onClick={() => loadConversations()} disabled={Boolean(deletingThread)}>Retry</button>
            </div>}
            {hasMore && !historyLoading && !historyError &&
              <button className="secondary" onClick={() => loadConversations(conversations.length)} disabled={Boolean(deletingThread)}>Load more</button>}
          </div>
        </section>
        <button className="secondary" onClick={onLogout}>
          Đăng xuất
        </button>
      </div>

      <div id="main">
        {tab === "chat" && <ChatView key={chatVersion} initialThreadId={activeThreadId}
          disabled={Boolean(deletingThread)}
          onThreadChange={setActiveThreadId} onBusyChange={setChatBusy}
          onNewChat={() => selectChat(null)} onTurnComplete={() => loadConversations()} />}
        {tab === "tickets" && <TicketsView />}
        {tab === "bookings" && <BookingsView />}
        {tab === "memory" && <MemoryView />}
      </div>
    </div>
  );
}

export default function App() {
  const [user, setUser] = useState(null);
  const [checking, setChecking] = useState(true);

  async function checkAuth() {
    if (!getToken()) {
      setUser(null);
      setChecking(false);
      return;
    }
    try {
      const me = await authApi.me();
      setUser(me);
    } catch {
      setToken(null);
      setUser(null);
    } finally {
      setChecking(false);
    }
  }

  useEffect(() => {
    checkAuth();
  }, []);

  function logout() {
    setToken(null);
    setUser(null);
  }

  if (checking) return null;

  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/login"
          element={user ? <Navigate to="/" replace /> : <LoginPage onLoggedIn={checkAuth} />}
        />
        <Route
          path="/register"
          element={user ? <Navigate to="/" replace /> : <RegisterPage onLoggedIn={checkAuth} />}
        />
        <Route
          path="/"
          element={user ? <MainApp user={user} onLogout={logout} /> : <Navigate to="/login" replace />}
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
