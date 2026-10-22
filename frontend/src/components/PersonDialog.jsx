import Modal from "./Modal";
import { avatarClass } from "../lib/days";

export default function PersonDialog({ person, schedules, onClose, onAddMedicine, onEdit, onRemoveMedicine, onRemovePerson }) {
  const meds = person
    ? schedules.filter((item) => item.person_name.toLowerCase() === person.toLowerCase())
    : [];
  return (
    <Modal open={Boolean(person)} onClose={onClose} wide label="Person details">
      {person && (
        <>
          <div className="modal-head">
            <span className={`avatar large ${avatarClass(person)}`}>{person.slice(0, 1).toUpperCase()}</span>
            <div>
              <h2>{person}</h2>
              <p className="lede">
                {meds.length
                  ? `${meds.length} scheduled ${meds.length === 1 ? "dose" : "doses"}`
                  : "No medicine yet. Add the first one."}
              </p>
            </div>
          </div>
          <ul className="meds">
            {meds.map((dose) => (
              <li key={dose.schedule_id}>
                <span>
                  <strong>{dose.dose_label} · {dose.time_spoken}</strong>
                  <span className="meta">{dose.days_spoken}</span>
                </span>
                <span className="row-actions">
                  <button type="button" className="btn ghost small" onClick={() => onEdit(dose)}>Edit</button>
                  <button type="button" className="btn ghost small danger" onClick={() => onRemoveMedicine(dose)}>Remove</button>
                </span>
              </li>
            ))}
          </ul>
          <div className="modal-actions spread">
            <button type="button" className="btn danger ghost" onClick={() => onRemovePerson(person)}>Remove person</button>
            <span>
              <button type="button" className="btn ghost" onClick={onClose}>Close</button>
              <button type="button" className="btn" onClick={onAddMedicine}>+ Add medicine</button>
            </span>
          </div>
        </>
      )}
    </Modal>
  );
}
