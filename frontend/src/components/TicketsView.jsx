import { useState, useEffect } from "react";
import { ticketApi } from "../api.js";

const formatAppTime = (value) => `${new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Ho_Chi_Minh",
  dateStyle: "medium",
  timeStyle: "medium",
}).format(new Date(value))} ICT`;

export default function TicketsView() {
  const [tickets, setTickets] = useState([]);
  const [content, setContent] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");

  async function load() {
    try {
      setTickets(await ticketApi.list());
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleCreate() {
    if (!content.trim() || !description.trim()) return alert("Cần nhập content và description");
    try {
      await ticketApi.create(content, description);
      setContent("");
      setDescription("");
      load();
    } catch (e) {
      alert(e.message);
    }
  }

  return (
    <div>
      <h3>Tickets</h3>
      <div className="card">
        <div className="form-row">
          <input placeholder="Content" value={content} onChange={(e) => setContent(e.target.value)} />
          <input placeholder="Description" value={description} onChange={(e) => setDescription(e.target.value)} />
        </div>
        <button onClick={handleCreate}>Tạo ticket</button>
      </div>

      {error && <div className="error">{error}</div>}
      {tickets.length === 0 && !error && <div className="empty">Chưa có ticket nào</div>}

      {tickets.map((t) => (
        <div className="card" key={t.ticket_code}>
          <b>{t.ticket_code}</b> <span className={`badge ${t.status}`}>{t.status}</span>
          <div>{t.content}</div>
          <div className="meta">{t.description}</div>
          <div className="meta">{formatAppTime(t.created_at)}</div>
        </div>
      ))}
    </div>
  );
}