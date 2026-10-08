import { useEffect, useState } from "react";

export type DeviceTier = "2d" | "static";

/** "static" under prefers-reduced-motion; "2d" otherwise. Phase 2 adds "3d" for laptops with WebGL. */
export function useDeviceTier(): DeviceTier {
  const query = () => (typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches ? "static" : "2d");
  const [tier, setTier] = useState<DeviceTier>(query);
  useEffect(() => {
    if (typeof matchMedia !== "function") return;
    const mq = matchMedia("(prefers-reduced-motion: reduce)");
    const on = () => setTier(query());
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return tier;
}
