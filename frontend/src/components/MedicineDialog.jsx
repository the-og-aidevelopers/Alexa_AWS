import { useEffect, useState } from "react";
import Modal from "./Modal";
import { ALL_DAYS, DAY_LABELS, WEEKDAYS, WEEKENDS } from "../lib/days";

// editing is null when adding, or the schedule item being changed.
export default function MedicineDialog({ open, person, editing, onClose, onSave }) {
  const [label, setLabel] = useState("");
  const [times, setTimes] = useState(["08:00"]);
  const [days, setDays] = useState(ALL_DAYS);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLabel(editing ? editing.dose_label : "");
    setTimes([editing ? editing.time_local : "08:00"]);
    setDays(editing ? editing.days : ALL_DAYS);
    setError("");
  }, [open, editing]);

  const toggleDay = (day) =>
    setDays((current) => (current.includes(day) ? current.filter((item) => item !== day) : [...current, day]));
  const setTime = (index, value) => setTimes((current) => current.map((item, i) => (i === index ? value : item)));

  async function submit(event) {
    event.preventDefault();
    if (!days.length) { setError("Pick at least one day."); return; }
    setSaving(true);
    const failure = await onSave({ dose_label: label, times: [...new Set(times.filter(Boolean))], days });
    setSaving(false);
    if (failure) setError(failure);
  }

  return (
    <Modal open={open} onClose={onClose} label="Medicine">
      <form onSubmit={submit}>
        <h2>{editing ? `Edit ${person}'s medicine` : `Add medicine for ${person}`}</h2>
        <label>
          Medicine
          <input value={label} onChange={(event) => setLabel(event.target.value)} required maxLength={60} placeholder="lisinopril" autoComplete="off" autoFocus />
        </label>
        <fieldset className="times">
          <legend>Times</legend>
          {times.map((value, index) => (
            <div className="time-row" key={index}>
              <input type="time" required value={value} onChange={(event) => setTime(index, event.target.value)} aria-label={`Time ${index + 1}`} />
              {!editing && times.length > 1 && (
                <button type="button" className="btn ghost small" aria-label="Remove this time" onClick={() => setTimes((c) => c.filter((_, i) => i !== index))}>×</button>
              )}
            </div>
          ))}
          {!editing && (
            <button type="button" className="btn ghost small" onClick={() => setTimes((c) => [...c, "20:00"])}>+ Another time</button>
          )}
        </fieldset>
        <fieldset className="days">
          <legend>Days</legend>
          <div className="day-presets">
            <button type="button" className="btn ghost small" onClick={() => setDays(ALL_DAYS)}>Every day</button>
            <button type="button" className="btn ghost small" onClick={() => setDays(WEEKDAYS)}>Weekdays</button>
            <button type="button" className="btn ghost small" onClick={() => setDays(WEEKENDS)}>Weekends</button>
          </div>
          <div className="day-picks">
            {DAY_LABELS.map((name, day) => (
              <label className="day-pick" key={name}>
                <input type="checkbox" checked={days.includes(day)} onChange={() => toggleDay(day)} />
                <span>{name}</span>
              </label>
            ))}
          </div>
        </fieldset>
        {error && <p className="form-error" role="status">{error}</p>}
        <div className="modal-actions">
          <button type="button" className="btn ghost" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn" disabled={saving}>{editing ? "Save changes" : "Add medicine"}</button>
        </div>
      </form>
    </Modal>
  );
}
