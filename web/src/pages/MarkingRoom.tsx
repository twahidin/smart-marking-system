import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import type { Crew } from "../api/types";
import { Notice } from "../components/Notice";
import { ThoughtPanel } from "../components/ThoughtPanel";
import { elapsed } from "../lib/format";
import { RoomScene2D } from "../scene/RoomScene2D";
import { useDeviceTier } from "../scene/useDeviceTier";
import { useRoomEvents } from "../scene/useRoomEvents";

const TILES: { key: "queued" | "read" | "mark" | "check" | "done" | "needs_you"; label: string }[] = [
  { key: "queued", label: "In the sorter" }, { key: "read", label: "Reading" }, { key: "mark", label: "Marking" },
  { key: "check", label: "Checking" }, { key: "done", label: "Done" }, { key: "needs_you", label: "Needs you" },
];

export function MarkingRoom() {
  const [params] = useSearchParams();
  const ca = params.get("ca") ? Number(params.get("ca")) : null;
  const { snapshot, error, live } = useRoomEvents(ca);
  const tier = useDeviceTier();
  const [picked, setPicked] = useState<{ id: number; crew: Crew; label: string } | null>(null);
  return (
    <div className="page room-page">
      <div className="page-header">
        <div>
          <h1>The Marking Room</h1>
          <p className="meta">Three crew members pass each script along the desks. Tap a name tag to read what they are thinking.</p>
        </div>
        <div className="actions">
          {snapshot?.started_at && <span className="pill pill-outline tabular">Started {elapsed(snapshot.started_at)}</span>}
          {!live && <span className="pill pill-amber">Live feed paused — refreshing every 5 s</span>}
          <Link className="btn btn-primary" to="/submissions/new">Feed the sorter</Link>
        </div>
      </div>
      {error && <Notice kind="error">{error}</Notice>}
      <div className="room-layout">
        <section className="room-main">
          <RoomScene2D desks={snapshot?.desks ?? []} tier={tier} onPick={(id, crew, label) => setPicked({ id, crew, label })} />
          <div className="room-tiles">
            {TILES.map((t) => (
              <div key={t.key} className={`room-tile tile-${t.key}`} aria-label={t.label}>
                <span className="label-caps">{t.label}</span>
                <strong className="tabular">{snapshot ? snapshot.counts[t.key] : "—"}</strong>
              </div>
            ))}
          </div>
        </section>
        <div className="room-side">
          {picked ? <ThoughtPanel submissionId={picked.id} crew={picked.crew} label={picked.label} onClose={() => setPicked(null)} />
                  : <div className="card"><h2>On the desks right now</h2>
                      {snapshot?.desks.length === 0 && <p className="muted">The desks are empty. Feed the sorter to start.</p>}
                      <ul className="desk-list">{snapshot?.desks.map((d) => <li key={d.submission_id}><i className={`dot dot-${d.stage}`} aria-hidden /><Link to={`/submissions/${d.submission_id}`}>{d.label}</Link><span className="muted tabular">{d.stage} · {elapsed(d.since)}</span></li>)}</ul>
                    </div>}
        </div>
      </div>
    </div>
  );
}
