import { NavLink, useNavigate } from "react-router-dom";
import { api } from "../api/client";

export function Nav({ needsYou }: { needsYou: number }) {
  const nav = useNavigate();
  // NavLink sets aria-current="page" on the active link by itself; app.css styles [aria-current="page"].
  return (
    <nav className="nav">
      <NavLink to="/classes" className="nav-brand" end>Smart Marking</NavLink>
      <div className="nav-links">
        <NavLink to="/classes">Classes</NavLink>
        <NavLink to="/submissions">Submissions</NavLink>
        <NavLink to="/assignments">Assignments</NavLink>
        <NavLink to="/review">Review {needsYou > 0 && <span className="key">{needsYou}</span>}</NavLink>
        <NavLink to="/learning">Learning</NavLink>
        <NavLink to="/settings">Settings</NavLink>
        <a href="#" onClick={async (e) => { e.preventDefault(); await api.post("/api/auth/logout"); nav("/sign-in"); }}>Sign out</a>
      </div>
    </nav>
  );
}
