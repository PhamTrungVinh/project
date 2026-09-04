import { useState, useEffect } from "react";
import { bookingApi } from "../api.js";

export default function BookingsView() {
  const [bookings, setBookings] = useState([]);
  const [reason, setReason] = useState("");
  const [time, setTime] = useState("");
  const [error, setError] = useState("");

  async function load() {
    try {
      setBookings(await bookingApi.list());
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleCreate() {
    if (!reason.trim() || !time.trim()) return alert("Cần nhập reason và time");
    try {
      await bookingApi.create(reason, time);
      setReason("");
      setTime("");
      load();
    } catch (e) {
      alert(e.message);
    }
  }

  async function handleCancel(code) {
    try {
      await bookingApi.cancel(code);
      load();
    } catch (e) {
      alert(e.message);
    }
  }

  return (
    <div>
      <h3>Bookings</h3>
      <div className="card">
        <div className="form-row">
          <input placeholder="Reason" value={reason} onChange={(e) => setReason(e.target.value)} />
          <input
            placeholder="Time (YYYY-MM-DDTHH:MM:SS)"
            value={time}
            onChange={(e) => setTime(e.target.value)}
          />
        </div>
        <button onClick={handleCreate}>Đặt phòng</button>
      </div>

      {error && <div className="error">{error}</div>}
      {bookings.length === 0 && !error && <div className="empty">Chưa có booking nào</div>}

      {bookings.map((b) => (
        <div className="card" key={b.booking_code}>
          <b>{b.booking_code}</b> <span className={`badge ${b.status}`}>{b.status}</span>
          <div>{b.reason}</div>
          <div className="meta">{new Date(b.time).toLocaleString()}</div>
          {b.status !== "Finished" && b.status !== "Canceled" && (
            <button className="danger" style={{ marginTop: 8 }} onClick={() => handleCancel(b.booking_code)}>
              Hủy
            </button>
          )}
        </div>
      ))}
    </div>
  );
}