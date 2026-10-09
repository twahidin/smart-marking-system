import { useCallback, useEffect, useRef, useState } from "react";

export const TOUR_STEP_MS = 3000;

/** Walks hotspots 0..count-1, one every 3 s, once round; index is -1 when not running. */
export function useTour(count: number): { index: number; running: boolean; toggle: () => void } {
  const [index, setIndex] = useState(-1);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const stop = useCallback(() => { if (timer.current) clearInterval(timer.current); timer.current = null; setIndex(-1); }, []);
  const toggle = useCallback(() => {
    if (timer.current) { stop(); return; }
    if (count === 0) return;
    setIndex(0);
    timer.current = setInterval(() => setIndex((i) => {
      if (i + 1 >= count) { if (timer.current) clearInterval(timer.current); timer.current = null; return -1; }
      return i + 1;
    }), TOUR_STEP_MS);
  }, [count, stop]);
  useEffect(() => () => { if (timer.current) clearInterval(timer.current); }, []);
  return { index, running: timer.current !== null && index >= 0, toggle };
}
