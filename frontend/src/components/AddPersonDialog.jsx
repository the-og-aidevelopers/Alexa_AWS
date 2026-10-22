import { useEffect, useState } from "react";
import Modal from "./Modal";

export default function AddPersonDialog({ open, onClose, onAdd }) {
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => { if (open) { setName(""); setError(""); } }, [open]);

  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    const failure = await onAdd(name);
    setSaving(false);
    if (failure) setError(failure);
  }

  return (
    <Modal open={open} onClose={onClose} label="Add a person">
      <form onSubmit={submit}>
        <h2>Add a person</h2>
        <p className="lede">Register someone in the household. You can add their medicines next.</p>
        <label>
          Name
          <input value={name} onChange={(event) => setName(event.target.value)} required maxLength={40} placeholder="Raj" autoComplete="off" autoFocus />
        </label>
        {error && <p className="form-error" role="status">{error}</p>}
        <div className="modal-actions">
          <button type="button" className="btn ghost" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn" disabled={saving}>Add person</button>
        </div>
      </form>
    </Modal>
  );
}
