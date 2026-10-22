import { useEffect, useState } from "react";

const STATE_LABEL = { taken: "Taken", due: "Due now", overdue: "Overdue", skipped: "Skipped", upcoming: "Later" };

function useClock() {
  const format = () => new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  const [clock, setClock] = useState(format);
  useEffect(() => {
    const id = setInterval(() => setClock(format()), 1000);
    return () => clearInterval(id);
  }, []);
  return clock;
}

export default function TodayPanel({ doses, alerts }) {
  const clock = useClock();
  return (
    <aside className="today" aria-labelledby="today-heading">
      <div className="today-head">
        <h2 id="today-heading">Today</h2>
        <span className="clock">{clock}</span>
      </div>
      <p className={`summary${alerts.length ? " is-alert" : ""}`}>
        {alerts.length === 0
          ? "Nothing is overdue."
          : `${alerts.length} ${alerts.length === 1 ? "dose is" : "doses are"} overdue.`}
      </p>
      <ul className="dose-board">
        {doses.length === 0 && <li className="empty">No doses scheduled for today.</li>}
        {doses.map((dose) => (
          <li key={dose.schedule_id}>
            <span className="dose-time">{dose.time_spoken}</span>
            <span className="dose-what">
              <strong>{dose.dose_label}</strong>
              <span className="meta">{dose.person_name}</span>
            </span>
            <span className={`state ${dose.state}`}>{STATE_LABEL[dose.state] || dose.state}</span>
          </li>
        ))}
      </ul>
      <p className="fine">A household log, not medical advice.</p>
    </aside>
  );
}
