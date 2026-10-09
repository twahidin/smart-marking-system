import { useCallback, useState } from "react";
import type { DeviceTier } from "./useDeviceTier";

const KEY = "sms.scene.labels";
const read = (): boolean | null => { try { const v = localStorage.getItem(KEY); return v === "on" ? true : v === "off" ? false : null; } catch { return null; } };
const coarse = () => typeof matchMedia === "function" && matchMedia("(pointer: coarse)").matches;

/** Show labels: remembered across visits; on by default where there is no hover (phones) and on the static tier. */
export function useSceneLabels(tier: DeviceTier): [boolean, (v: boolean) => void] {
  const [on, setOn] = useState<boolean>(() => read() ?? (tier === "static" || coarse()));
  const set = useCallback((v: boolean) => { setOn(v); try { localStorage.setItem(KEY, v ? "on" : "off"); } catch { /* private mode */ } }, []);
  return [on, set];
}
