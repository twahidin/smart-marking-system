import { useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { Button } from "../components/Button";
import { Notice } from "../components/Notice";
import { Hero } from "../components/Hero";

export function SignIn() {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const nav = useNavigate();
  const from = (useLocation().state as any)?.from ?? "/classes";
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setError(null);
    try { await api.post("/api/auth/login", { password }); nav(from, { replace: true }); }
    catch (err) {
      if (err instanceof ApiError && err.code === "needs_setup") { nav("/setup", { replace: true }); return; }
      setError(err instanceof ApiError ? err.message : "Could not sign in");
    }
    finally { setBusy(false); }
  };
  return (
    <div className="sign-in">
      <Hero>Smart agentic helpers at your service while you rest.</Hero>
      <div className="form">
        <form onSubmit={submit}>
          <h1 style={{ fontSize: 36 }}>Sign in</h1>
          <p className="meta">Teachers only. Enter the password your school set when it deployed Smart Marking.</p>
          {error && <Notice>{error}</Notice>}
          <div className="field" style={{ marginTop: 20 }}>
            <label htmlFor="pw">Password</label>
            <input id="pw" className="input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </div>
          <Button type="submit" variant="primary" size="lg" wide disabled={busy || !password}>{busy ? "Signing in…" : "Sign in"}</Button>
        </form>
        <p className="tertiary" style={{ fontSize: 12 }}>Smart Marking · self-hosted on Railway</p>
      </div>
    </div>
  );
}
