import { useCallback, useState } from "react";
import type { DeviceTier } from "./useDeviceTier";

const KEY = "sms.scene.film";
const saveData = () => Boolean((navigator as Navigator & { connection?: { saveData?: boolean } }).connection?.saveData);
const readOff = () => { try { return sessionStorage.getItem(KEY) === "off"; } catch { return false; } };

/** Whether a scene may play its film loop: never on the static tier or under Save-Data, and not after the teacher switched it off this session. */
export function useFilm(tier: DeviceTier): [boolean, (v: boolean) => void] {
  const [wanted, setWanted] = useState(() => !readOff());
  const set = useCallback((v: boolean) => { setWanted(v); try { if (v) sessionStorage.removeItem(KEY); else sessionStorage.setItem(KEY, "off"); } catch { /* ignore */ } }, []);
  return [wanted && tier === "2d" && !saveData(), set];
}
