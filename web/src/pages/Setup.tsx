import { useEffect, useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { Button } from "../components/Button";
import { Notice } from "../components/Notice";
import { Hero } from "../components/Hero";

const MIN = 8;

/** First-run wizard, step 1 of 2: the person who opens a fresh deployment creates the teacher password.
 *  Step 2 (connect a model) is the Settings page itself, reached with ?setup=1. */
export function Setup() {
  const [needs, setNeeds] = useState<boolean | null>(null);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const nav = useNavigate();
  useEffect(() => {
    api.get<{ needs_setup: boolean }>("/api/setup/status").then((s) => setNeeds(s.needs_setup), () => setNeeds(true));
  }, []);
  if (needs === null) return <p className="page muted">Loading…</p>;
  if (!needs) return <Navigate to="/sign-in" replace />;
  const tooShort = password.length > 0 && password.length < MIN;
  const mismatch = confirm.length > 0 && confirm !== password;
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (password.length < MIN) { setError(`Use at least ${MIN} characters.`); return; }
    if (confirm !== password) { setError("The two passwords don't match."); return; }
    setBusy(true); setError(null);
    try { await api.post("/api/setup", { password }); nav("/settings?setup=1", { replace: true }); }
    catch (err) {
      if (err instanceof ApiError && err.code === "already_set_up") { nav("/sign-in", { replace: true }); return; }
      setError(err instanceof ApiError ? err.message : "Could not finish setup — check your connection and try again");
    } finally { setBusy(false); }
  };
  return (
    <div className="sign-in">
      <Hero>One deployment, one password, one key — then your class can hand in.</Hero>
      <div className="form">
        <form onSubmit={submit} aria-label="Set up Smart Marking">
          <p className="eyebrow" style={{ letterSpacing: ".06em", textTransform: "uppercase", fontSize: 12, fontWeight: 700 }}>Step 1 of 2</p>
          <h1 style={{ fontSize: 36 }}>Create the teacher password</h1>
          <p className="meta">This is the password every teacher at your school will use to sign in. Nothing to copy from Railway.</p>
          <Notice>Do this now — until a password is set, anyone who has this address could set it.</Notice>
          {error && <Notice kind="error">{error}</Notice>}
          <div className="field" style={{ marginTop: 20 }}>
            <label htmlFor="setup-pw">Password</label>
            <input id="setup-pw" className="input" type="password" autoComplete="new-password" value={password}
              onChange={(e) => setPassword(e.target.value)} required minLength={MIN} aria-invalid={tooShort || undefined} />
            <span className="help">At least {MIN} characters. You can change it later under Settings.</span>
          </div>
          <div className="field">
            <label htmlFor="setup-pw2">Type it again</label>
            <input id="setup-pw2" className="input" type="password" autoComplete="new-password" value={confirm}
              onChange={(e) => setConfirm(e.target.value)} required aria-invalid={mismatch || undefined} />
          </div>
          <Button type="submit" variant="primary" size="lg" wide disabled={busy || !password || !confirm}>{busy ? "Setting up…" : "Set password and continue"}</Button>
        </form>
        <p className="tertiary" style={{ fontSize: 12 }}>Next: connect a model (paste an API key).</p>
      </div>
    </div>
  );
}
