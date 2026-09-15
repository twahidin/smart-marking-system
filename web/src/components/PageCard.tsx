export function PageCard({ src, index, onRemove, onMoveLeft, onMoveRight }:
  { src: string; index: number; onRemove?: () => void; onMoveLeft?: () => void; onMoveRight?: () => void }) {
  return (
    <div className="pg">
      <img src={src} alt={`Page ${index + 1}`} className="grayscale" />
      <span className="tag-n">{index + 1}</span>
      {(onRemove || onMoveLeft || onMoveRight) && (
        <div className="pg-actions">
          {onMoveLeft && <button type="button" className="btn btn-ghost btn-sm" onClick={onMoveLeft} aria-label={`Move page ${index + 1} earlier`}>←</button>}
          {onMoveRight && <button type="button" className="btn btn-ghost btn-sm" onClick={onMoveRight} aria-label={`Move page ${index + 1} later`}>→</button>}
          {onRemove && <button type="button" className="btn btn-ghost btn-sm" onClick={onRemove}>Delete</button>}
        </div>
      )}
    </div>
  );
}
