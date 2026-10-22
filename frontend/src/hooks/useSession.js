import { useCallback, useEffect, useState } from "react";
import { api } from "../api";

export function useSession() {
  const [state, setState] = useState({ loading: true, authenticated: false, provider: "local", identity: null, error: "" });

  useEffect(() => {
    let live = true;
    api
      .session()
      .then(({ body }) => {
        if (live) setState({ loading: false, authenticated: Boolean(body.authenticated), provider: body.provider, identity: body.identity, error: "" });
      })
      .catch(() => {
        if (live) setState((current) => ({ ...current, loading: false, error: "Session unavailable. Reload to retry." }));
      });
    return () => { live = false; };
  }, []);

  const signOut = useCallback(async () => {
    const { ok } = await api.logout();
    if (ok) window.location.replace("/login");
    return ok;
  }, []);

  return { ...state, signOut };
}
