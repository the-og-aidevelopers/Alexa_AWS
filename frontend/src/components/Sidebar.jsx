import { avatarClass } from "../lib/days";
import Logo from "./Logo";

export default function Sidebar({ session, people, onAdd, onOpen }) {
  return (
    <aside className="sidebar" aria-label="People">
      <div className="brand">
        <Logo size={40} />
        <h1>Pillow</h1>
      </div>

      <p className="side-label">People</p>
      <ul className="people">
        {people.length === 0 && <li className="empty">No one yet.</li>}
        {people.map((name) => (
          <li key={name}>
            <button type="button" className="person" onClick={() => onOpen(name)}>
              <span className={`avatar ${avatarClass(name)}`}>{name.slice(0, 1).toUpperCase()}</span>
              <strong>{name}</strong>
            </button>
          </li>
        ))}
      </ul>
      <button type="button" className="add-person" onClick={onAdd}>+ Add person</button>

      <div className="side-foot">
        <a href="/agent">Open voice view</a>
        <span className="who-home">{session.identity?.household_name}</span>
        {(session.provider === "local" || session.provider === "cognito") && (
          <button type="button" className="link-button" onClick={session.signOut}>Sign out</button>
        )}
      </div>
    </aside>
  );
}
