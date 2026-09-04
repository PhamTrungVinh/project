import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { authApi, setToken, getApiBase, setApiBase } from "../api.js";

export default function LoginPage({ onLoggedIn }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [apiBase, setApiBaseState] = useState(getApiBase());
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  async function handleLogin() {
    setError("");
    if (!email.trim() || !password.trim()) {
      setError("Vui lòng nhập đầy đủ Email và Password.");
      return;
    }
    setLoading(true);
    try {
      const data = await authApi.login(email, password);
      setToken(data.access_token);
      await onLoggedIn();
      navigate("/");
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-screen">
      <h2>Đăng nhập</h2>
      {error && <div className="error">{error}</div>}
      <input
        type="email"
        placeholder="Email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
      />
      <input
        type="password"
        placeholder="Password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && handleLogin()}
      />
      <button style={{ width: "100%", marginTop: 10 }} onClick={handleLogin} disabled={loading}>
        {loading ? "Đang đăng nhập..." : "Đăng nhập"}
      </button>

      <p className="auth-switch">
        Chưa có tài khoản? <Link to="/register">Đăng ký ngay</Link>
      </p>

      <div style={{ marginTop: 16 }}>
        <input
          type="text"
          value={apiBase}
          onChange={(e) => {
            setApiBaseState(e.target.value);
            setApiBase(e.target.value);
          }}
          placeholder="API base URL"
        />
      </div>
    </div>
  );
}