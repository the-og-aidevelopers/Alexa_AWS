export default function ReminderBanner({ text, onClose }) {
  if (!text) return null;
  return (
    <div className="reminder" role="alert">
      <span className="ring" aria-hidden="true" />
      <div className="reminder-text">
        <strong>Reminder</strong>
        <p>{text}</p>
      </div>
      <button type="button" className="reminder-close" aria-label="Dismiss reminder" onClick={onClose}>×</button>
    </div>
  );
}
