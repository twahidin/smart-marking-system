export function PagePager({ count, current, onSelect }: { count: number; current: number; onSelect: (i: number) => void }) {
  return (
    <div className="pager" role="tablist" aria-label="Pages">
      {Array.from({ length: count }, (_, i) => (
        <button key={i} role="tab" aria-selected={i === current} className={i === current ? "on" : ""} onClick={() => onSelect(i)}>{i + 1}</button>
      ))}
    </div>
  );
}
