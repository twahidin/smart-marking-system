import { useEffect, useState, type RefObject } from "react";

/** True while the element is on screen. Reports true where IntersectionObserver is missing (jsdom, old browsers). */
export function useInView(ref: RefObject<Element | null>): boolean {
  const supported = typeof IntersectionObserver === "function";
  const [inView, setInView] = useState(!supported);
  useEffect(() => {
    const el = ref.current;
    if (!supported || !el) return;
    const io = new IntersectionObserver((entries) => { for (const e of entries) setInView(e.isIntersecting); }, { rootMargin: "120px" });
    io.observe(el);
    return () => io.disconnect();
  }, [ref, supported]);
  return inView;
}
