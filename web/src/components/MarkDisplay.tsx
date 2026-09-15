export function MarkDisplay({ earned, max, upper, squares = true }: { earned: number; max: number; upper?: number; squares?: boolean }) {
  const hi = upper ?? earned;
  return (
    <span className="mark" aria-label={`${earned}${hi !== earned ? ` to ${hi}` : ""} out of ${max}`}>
      {squares && max <= 30 && (
        <span className="sq" aria-hidden>
          {Array.from({ length: max }, (_, i) => <i key={i} className={i < earned ? "on" : ""} />)}
        </span>
      )}
      <span>{earned}{hi !== earned && <span className="upper">–{hi}</span>} / {max}</span>
    </span>
  );
}
