async function request(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: options.body ? { "Content-Type": "application/json", ...options.headers } : options.headers,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  const body = await response.json().catch(() => ({}));
  return { ok: response.ok, status: response.status, body };
}

export const api = {
  session: () => request("/api/auth/session"),
  login: (data) => request("/api/auth/login", { method: "POST", body: data }),
  register: (data) => request("/api/auth/register", { method: "POST", body: data }),
  logout: () => request("/api/auth/logout", { method: "POST" }),
  today: () => request("/api/today"),
  reminders: () => request("/api/reminders"),
  talk: (utterance, speaker) => request("/api/talk", { method: "POST", body: { utterance, speaker } }),
  addPerson: (name) => request("/api/people", { method: "POST", body: { name } }),
  removePerson: (name) => request(`/api/people/${encodeURIComponent(name)}`, { method: "DELETE" }),
  addSchedule: (data) => request("/api/schedules", { method: "POST", body: data }),
  updateSchedule: (id, data) => request(`/api/schedules/${id}`, { method: "PUT", body: data }),
  removeSchedule: (id) => request(`/api/schedules/${id}`, { method: "DELETE" }),
};
