import { useCallback, useEffect, useRef } from "react";
import { api } from "../api";

const KEY = "dose-reminders-announced";

function loadSeen() {
  try { return new Set(JSON.parse(window.sessionStorage.getItem(KEY) || "[]")); } catch { return new Set(); }
}

// Polls for doses starting within the next few minutes and announces each one once per day.
// This is the message a smart speaker would say ahead of time, for example
// "Mom's lisinopril is due at 8 AM, in 10 minutes."
export function useReminders(onAnnounce, intervalMs = 20000) {
  const handler = useRef(onAnnounce);
  handler.current = onAnnounce;
  const seen = useRef(null);

  const check = useCallback(async () => {
    if (seen.current === null) seen.current = loadSeen();
    const { ok, body } = await api.reminders();
    if (!ok || !body.reminders) return;
    const day = new Date().toDateString();
    for (const reminder of body.reminders) {
      const key = `${day}-${reminder.schedule_id}`;
      if (seen.current.has(key)) continue;
      seen.current.add(key);
      try { window.sessionStorage.setItem(KEY, JSON.stringify([...seen.current])); } catch { /* private mode */ }
      handler.current(reminder);
    }
  }, []);

  useEffect(() => {
    check();
    const id = setInterval(check, intervalMs);
    return () => clearInterval(id);
  }, [check, intervalMs]);

  return check;
}
