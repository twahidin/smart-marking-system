import type { Band } from "../api/types";

type Props = { bands: Band[]; value: string | null; onChange: (band: string) => void; proposed?: string | null; disabled?: boolean };

export const bandMax = (bands: Band[]): number => bands.reduce((s, b) => Math.max(s, b.marks), 0);

/** The rubric criterion's bands as radios, each with its marks and descriptor: pick the band the response reaches. */
export function BandPicker({ bands, value, onChange, proposed, disabled = false }: Props) {
  const chosen = bands.find((b) => b.band === value) ?? null;
  return (
    <table className="table criteria picker" aria-label="Bands">
      <thead><tr><th>Band</th><th className="num">Proposed</th><th className="num" style={{ width: 88 }}>Your mark</th></tr></thead>
      <tbody>
        {bands.map((b, i) => (
          <tr key={`${b.band}-${i}`}>
            <td>
              <label className="pick" style={{ display: "flex", alignItems: "flex-start", gap: 10, minHeight: 40, cursor: disabled ? "default" : "pointer" }}>
                <input type="radio" name="band" checked={value === b.band} disabled={disabled} onChange={() => onChange(b.band)} aria-label={`Band ${b.band} · ${b.marks} mark${b.marks === 1 ? "" : "s"}`} style={{ width: 18, height: 18, marginTop: 2 }} />
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
