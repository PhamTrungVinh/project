import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { authApi, setToken } from "../api.js";

export default function RegisterPage({ onLoggedIn }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  async function handleRegister() {
    setError("");
    if (!email.trim() || !password.trim()) {
      setError("Vui lòng nhập đầy đủ Email và Password.");
      return;
    }
    setLoading(true);
    try {
      await authApi.register(email, password, fullName);
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
      <h2>Đăng ký tài khoản</h2>
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
      />
      <input
        type="text"
        placeholder="Full name (tùy chọn)"
        value={fullName}
        onChange={(e) => setFullName(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && handleRegister()}
      />
      <button style={{ width: "100%", marginTop: 10 }} onClick={handleRegister} disabled={loading}>
        {loading ? "Đang đăng ký..." : "Đăng ký"}
      </button>

      <p className="auth-switch">
        Đã có tài khoản? <Link to="/login">Đăng nhập</Link>
      </p>
    </div>
  );
}