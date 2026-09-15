import { useCallback, useEffect, useState } from "react";
import { Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { api, ApiError } from "./api/client";
import type { QueueItem } from "./api/types";
import { Nav } from "./components/Nav";
import { Learning } from "./pages/Learning";
import { NewSubmission } from "./pages/NewSubmission";
import { Review } from "./pages/Review";
import { Settings } from "./pages/Settings";
import { SignIn } from "./pages/SignIn";
import { SubmissionDetail } from "./pages/SubmissionDetail";
import { Submissions } from "./pages/Submissions";

function Shell() {
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [needsYou, setNeedsYou] = useState(0);
  const loc = useLocation();
  const refreshQueue = useCallback(async () => {
    try { setNeedsYou((await api.get<QueueItem[]>("/api/queue")).length); } catch { /* ignore */ }
  }, []);
  useEffect(() => {
    api.get("/api/auth/me").then(() => setAuthed(true)).catch((e) => setAuthed(!(e instanceof ApiError && e.status === 401)));
  }, []);
  useEffect(() => { if (authed) refreshQueue(); }, [authed, loc.pathname, refreshQueue]);
  if (authed === null) return <p className="page muted">Loading…</p>;
  if (!authed) return <Navigate to="/sign-in" replace state={{ from: loc.pathname }} />;
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
        <Route path="/review" element={<Review />} />
        <Route path="/learning" element={<Learning />} />
        <Route path="/settings" element={<Settings />} />
      </Route>
      <Route path="*" element={<Navigate to="/submissions" replace />} />
    </Routes>
  );
}
