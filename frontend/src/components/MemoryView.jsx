import { useState } from "react";
import { chatApi } from "../api.js";

export default function MemoryView() {
  const [fact, setFact] = useState("");
  const [result, setResult] = useState("");

  async function handleAddFact() {
    if (!fact.trim()) return;
    try {
      await chatApi.addFact(fact);
      setFact("");
      setResult("✅ Đã lưu fact.");
    } catch (e) {
      setResult("❌ " + e.message);
    }
  }

  async function handleClear() {
    if (!confirm("Xóa toàn bộ memory?")) return;
    try {
      const r = await chatApi.clearMemory();
      setResult(`✅ Đã xóa ${r.facts_deleted} facts, ${r.episodes_deleted} episodes.`);
    } catch (e) {
      setResult("❌ " + e.message);
    }
  }

  return (
    <div>
      <h3>Memory</h3>
      <div className="card">
        <input
          placeholder="VD: I prefer concise answers"
          value={fact}
          onChange={(e) => setFact(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleAddFact()}
        />
        <button onClick={handleAddFact}>Lưu fact</button>
      </div>
      <div className="card">
        <p style={{ marginTop: 0, color: "var(--muted)" }}>
          Xóa toàn bộ Semantic + Episodic memory của tài khoản này.
        </p>
        <button className="danger" onClick={handleClear}>
          🗑️ Xóa toàn bộ memory
        </button>
      </div>
      {result && <div style={{ marginTop: 10 }}>{result}</div>}
    </div>
  );
}