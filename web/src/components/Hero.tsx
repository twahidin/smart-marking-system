import { ART, FRAMES } from "../scene/art";
import { Frames } from "../scene/Frames";
import { useDeviceTier } from "../scene/useDeviceTier";

/** The sign-in and setup pages' left panel: the brand, the teacher with feet up while the crew marks (with its frame cycle on the live tier), and a line under it. */
export function Hero({ children }: { children: React.ReactNode }) {
  const tier = useDeviceTier();
  return (
    <div className="hero">
      <span className="nav-brand">Smart Marking</span>
      <div className="hero-art">
        <img src={ART.hero} alt="" width={1800} height={1005} />
        {tier !== "static" && <Frames frames={FRAMES.hero} />}
      </div>
      <p>{children}</p>
    </div>
  );
}
