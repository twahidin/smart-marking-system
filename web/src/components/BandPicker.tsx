import type { Band } from "../api/types";

type Props = {
  bands: Band[]; value: string | null;
  /** `marks` is only sent for a criterion the rubric has no bands for: 0 to award nothing instead of the proposal. */
  onChange: (band: string, marks?: number) => void;
  proposed?: string | null; proposedMarks?: number | null; marks?: number | null; disabled?: boolean;
};

export const bandMax = (bands: Band[]): number => bands.reduce((s, b) => Math.max(s, b.marks), 0);
const plural = (n: number) => `${n} mark${n === 1 ? "" : "s"}`;

/** The rubric criterion's bands as radios, each with its marks and descriptor: pick the band the response reaches.
 *  A criterion the rubric has no bands for (the marker invented it, or the row is empty) cannot be validated, so
 *  the proposed band is the only option, with its marks, or 0. */
export function BandPicker({ bands, value, onChange, proposed, proposedMarks, marks, disabled = false }: Props) {
  if (bands.length === 0) {
    const band = proposed ?? "";
    const pm = proposedMarks ?? 0;
    const zero = value !== null && marks === 0;
    const picked = value !== null && !zero;
    const yours = value === null ? "—" : zero ? 0 : pm;
    return (
      <div>
        <p className="help" role="note">This criterion is not in the rubric — accept the proposed band or award 0.</p>
        <table className="table criteria picker" aria-label="Bands">
          <thead><tr><th>Band</th><th className="num">Proposed</th><th className="num" style={{ width: 88 }}>Your mark</th></tr></thead>
          <tbody>
            <tr>
              <td>
                <label className="pick" style={{ display: "flex", alignItems: "flex-start", gap: 10, minHeight: 40, cursor: disabled ? "default" : "pointer" }}>
                  <input type="radio" name="band" checked={picked} disabled={disabled || !band} onChange={() => onChange(band)} aria-label={`Band ${band} · ${plural(pm)} (proposed)`} style={{ width: 18, height: 18, marginTop: 2 }} />
                  <span><strong>Band {band || "—"}</strong><div className="help">The marker’s proposal</div></span>
                </label>
              </td>
              <td className="num">✓</td>
              <td className="num">{pm}</td>
            </tr>
            <tr>
              <td>
                <label className="pick" style={{ display: "flex", alignItems: "flex-start", gap: 10, minHeight: 40, cursor: disabled ? "default" : "pointer" }}>
                  <input type="radio" name="band" checked={zero} disabled={disabled || !band} onChange={() => onChange(band, 0)} aria-label="Award 0 marks" style={{ width: 18, height: 18, marginTop: 2 }} />
                  <span><strong>Award 0</strong><div className="help">Nothing for this criterion</div></span>
                </label>
              </td>
              <td className="num"></td>
              <td className="num">0</td>
            </tr>
          </tbody>
          <tfoot><tr><td>Criterion total</td><td className="num">{pm} / {pm}</td><td className="num" style={{ fontSize: 18 }} aria-label="Your mark">{yours} / {pm}</td></tr></tfoot>
        </table>
      </div>
    );
  }
  const chosen = bands.find((b) => b.band === value) ?? null;
  return (
    <table className="table criteria picker" aria-label="Bands">
      <thead><tr><th>Band</th><th className="num">Proposed</th><th className="num" style={{ width: 88 }}>Your mark</th></tr></thead>
      <tbody>
        {bands.map((b, i) => (
          <tr key={`${b.band}-${i}`}>
            <td>
              <label className="pick" style={{ display: "flex", alignItems: "flex-start", gap: 10, minHeight: 40, cursor: disabled ? "default" : "pointer" }}>
                <input type="radio" name="band" checked={value === b.band} disabled={disabled} onChange={() => onChange(b.band)} aria-label={`Band ${b.band} · ${plural(b.marks)}`} style={{ width: 18, height: 18, marginTop: 2 }} />
                <span><strong>Band {b.band}</strong>{b.descriptor && <div className="help">{b.descriptor}</div>}</span>
              </label>
            </td>
            <td className="num">{proposed === b.band ? "✓" : ""}</td>
            <td className="num">{b.marks}</td>
          </tr>
        ))}
      </tbody>
      <tfoot><tr><td>Criterion total</td><td className="num">{proposed ? `${bands.find((b) => b.band === proposed)?.marks ?? "—"} / ${bandMax(bands)}` : "—"}</td><td className="num" style={{ fontSize: 18 }} aria-label="Your mark">{chosen ? chosen.marks : "—"} / {bandMax(bands)}</td></tr></tfoot>
    </table>
  );
}
