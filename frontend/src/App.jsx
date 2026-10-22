import { useEffect } from "react";
import Dashboard from "./pages/Dashboard";
import Agent from "./pages/Agent";
import Login from "./pages/Login";
import { useSession } from "./hooks/useSession";

export function pageFor(pathname) {
  if (pathname.startsWith("/login")) return "login";
  if (pathname.startsWith("/agent")) return "agent";
  return "dashboard";
}

export default function App() {
  const page = pageFor(window.location.pathname);
  const session = useSession();

  useEffect(() => {
    if (session.loading) return;
    if (page !== "login" && !session.authenticated) window.location.replace("/login");
    if (page === "login" && session.authenticated) window.location.replace("/");
  }, [page, session.loading, session.authenticated]);

  if (page === "login") return <Login session={session} />;
  if (session.loading || !session.authenticated) {
    return <p className="boot">{session.error || "Loading…"}</p>;
  }
  return page === "agent" ? <Agent session={session} /> : <Dashboard session={session} />;
}
