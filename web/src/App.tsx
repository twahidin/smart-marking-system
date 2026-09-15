import { useCallback, useEffect, useState } from "react";
import { Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { api, ApiError } from "./api/client";
import type { QueueItem } from "./api/types";
import { Button } from "./components/Button";
import { Nav } from "./components/Nav";
import { Notice } from "./components/Notice";
import { Assignments } from "./pages/Assignments";
import { Learning } from "./pages/Learning";
import { NewSubmission } from "./pages/NewSubmission";
import { Review } from "./pages/Review";
import { Settings } from "./pages/Settings";
import { SignIn } from "./pages/SignIn";
import { SubmissionDetail } from "./pages/SubmissionDetail";
import { Submissions } from "./pages/Submissions";

type AuthState = "loading" | "authed" | "anon" | "error";

function Shell() {
  const [auth, setAuth] = useState<AuthState>("loading");
  const [needsYou, setNeedsYou] = useState(0);
  const loc = useLocation();
  const refreshQueue = useCallback(async () => {
    try { setNeedsYou((await api.get<QueueItem[]>("/api/queue")).length); } catch { /* ignore */ }
  }, []);
  const checkAuth = useCallback(() => {
    setAuth("loading");
    api.get("/api/auth/me").then(
      () => setAuth("authed"),
      (e) => setAuth(e instanceof ApiError && e.status === 401 ? "anon" : "error"),
    );
  }, []);
  useEffect(() => { checkAuth(); }, [checkAuth]);
  useEffect(() => { if (auth === "authed") refreshQueue(); }, [auth, loc.pathname, refreshQueue]);
  if (auth === "loading") return <p className="page muted">Loading…</p>;
  if (auth === "anon") return <Navigate to="/sign-in" replace state={{ from: loc.pathname }} />;
  if (auth === "error") {
    return (
      <div className="page">
        <Notice kind="error">
          Can't reach Smart Marking right now.
          <div style={{ marginTop: 12 }}>
            <Button variant="secondary" onClick={checkAuth}>Try again</Button>
          </div>
        </Notice>
      </div>
    );
  }
  return <><Nav needsYou={needsYou} /><Outlet context={{ refreshQueue }} /></>;
}

export function App() {
  return (
    <Routes>
      <Route path="/sign-in" element={<SignIn />} />
      <Route element={<Shell />}>
        <Route index element={<Navigate to="/submissions" replace />} />
        <Route path="/submissions" element={<Submissions />} />
        <Route path="/submissions/new" element={<NewSubmission />} />
        <Route path="/submissions/:id" element={<SubmissionDetail />} />
        <Route path="/assignments" element={<Assignments />} />
        <Route path="/review" element={<Review />} />
        <Route path="/learning" element={<Learning />} />
        <Route path="/settings" element={<Settings />} />
      </Route>
      <Route path="*" element={<Navigate to="/submissions" replace />} />
    </Routes>
  );
}
