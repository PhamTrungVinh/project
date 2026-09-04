const DEFAULT_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export function getApiBase() {
  return localStorage.getItem("fpt_api_base") || DEFAULT_BASE;
}

export function setApiBase(url) {
  localStorage.setItem("fpt_api_base", url);
}

export function getToken() {
  return localStorage.getItem("fpt_token");
}

export function setToken(token) {
  if (token) localStorage.setItem("fpt_token", token);
  else localStorage.removeItem("fpt_token");
}

export async function apiFetch(path, options = {}) {
  const token = getToken();
  const headers = { ...(options.headers || {}) };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (options.body && !(options.body instanceof URLSearchParams)) {
    headers["Content-Type"] = "application/json";
  }

  const res = await fetch(getApiBase() + path, { ...options, headers });
  const isJson = res.headers.get("content-type")?.includes("application/json");
  const data = isJson ? await res.json() : null;

  if (!res.ok) {
    const msg = data?.detail || res.statusText;
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return data;
}

export const authApi = {
  register: (email, password, full_name) =>
    apiFetch("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, full_name: full_name || null }),
    }),
  login: (email, password) => {
    const form = new URLSearchParams();
    form.set("username", email);
    form.set("password", password);
    return apiFetch("/auth/login", { method: "POST", body: form });
  },
  me: () => apiFetch("/users/me"),
};

export const chatApi = {
  send: (message, thread_id) =>
    apiFetch("/chat/", { method: "POST", body: JSON.stringify(thread_id ? { message, thread_id } : { message }) }),
  listConversations: () => apiFetch("/chat/conversations"),
  addFact: (fact) => apiFetch("/chat/memory/fact", { method: "POST", body: JSON.stringify({ fact }) }),
  clearMemory: () => apiFetch("/chat/memory", { method: "DELETE" }),
};

export const ticketApi = {
  list: () => apiFetch("/tickets/"),
  create: (content, description) =>
    apiFetch("/tickets/", { method: "POST", body: JSON.stringify({ content, description }) }),
};

export const bookingApi = {
  list: () => apiFetch("/bookings/"),
  create: (reason, time) =>
    apiFetch("/bookings/", { method: "POST", body: JSON.stringify({ reason, time }) }),
  cancel: (code) => apiFetch(`/bookings/${code}/cancel`, { method: "POST" }),
};