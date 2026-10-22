import { useState } from "react";
import { api } from "../api";
import Logo from "../components/Logo";
import "../styles/dashboard.css";
import "../styles/login.css";

export default function Login({ session }) {
  const [form, setForm] = useState({ email: "", password: "", household_name: "" });
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const cognito = !session.loading && session.provider === "cognito" && Boolean(session.loginUrl);
  const external = !session.loading && session.provider !== "local" && !cognito;

  const set = (key) => (event) => setForm((current) => ({ ...current, [key]: event.target.value }));

  async function submit(action) {
    if (busy) return;
    if (action === "register" && !form.household_name.trim()) {
      setMessage("Enter a household name to create a new account.");
      return;
    }
    setBusy(true);
    setMessage("Please wait…");
    try {
      const { ok, body } = await (action === "register" ? api.register(form) : api.login(form));
      if (!ok) throw new Error(body.error);
      window.location.assign("/");
    } catch (error) {
      setMessage(error.message || "Unable to sign in.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-page">
      <section className="login-card">
        <Logo size={64} className="login-logo" />
        <p className="eyebrow">Pillow</p>
        <h1>Caregiver sign in</h1>
        {cognito ? (
          <>
            <p className="lede">Sign in or create an account with your email to manage your family's medicines.</p>
            <div className="login-actions">
              <button type="button" className="btn" onClick={() => window.location.assign(session.loginUrl)}>
                Sign in
              </button>
            </div>
          </>
        ) : external ? (
          <p className="lede">
            This deployment uses an external identity provider. Use its authenticated client. Local password login is disabled.
          </p>
        ) : (
          <form
            onSubmit={(event) => {
              event.preventDefault();
              if (event.currentTarget.reportValidity()) submit("login");
            }}
          >
            <p className="lede">Create an account to manage your family's schedule.</p>
            <label>
              Email
              <input type="email" required autoComplete="username" maxLength={254} value={form.email} onChange={set("email")} />
            </label>
            <label>
              Password (at least 12 characters)
              <input type="password" required minLength={12} maxLength={256} autoComplete="current-password" value={form.password} onChange={set("password")} />
            </label>
            <label>
              Household name (for a new account)
              <input maxLength={80} placeholder="Sharma family" value={form.household_name} onChange={set("household_name")} />
            </label>
            <div className="login-actions">
              <button
                type="button"
                className="btn ghost"
                disabled={busy}
                onClick={(event) => { if (event.currentTarget.form.reportValidity()) submit("register"); }}
              >
                Create household
              </button>
              <button type="submit" className="btn" disabled={busy}>Sign in</button>
            </div>
            {message && <p className="form-error" role="status">{message}</p>}
          </form>
        )}
      </section>
    </div>
  );
}
