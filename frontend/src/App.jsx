import { useState, useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import LoginPage from "./components/LoginPage.jsx";
import RegisterPage from "./components/RegisterPage.jsx";
import ChatView from "./components/ChatView.jsx";
import TicketsView from "./components/TicketsView.jsx";
import BookingsView from "./components/BookingsView.jsx";
import MemoryView from "./components/MemoryView.jsx";
import { authApi, getToken, setToken } from "./api.js";

const TABS = [
  { id: "chat", label: "💬 Chat" },
  { id: "tickets", label: "🎫 Tickets" },
  { id: "bookings", label: "📅 Bookings" },
  { id: "memory", label: "🧠 Memory" },
];

function MainApp({ user, onLogout }) {
  const [tab, setTab] = useState("chat");

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
          >
            {t.label}
          </button>
        ))}
        <div style={{ flex: 1 }} />
        <button className="secondary" onClick={onLogout}>
          Đăng xuất
        </button>
      </div>

      <div id="main">
        {tab === "chat" && <ChatView />}
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