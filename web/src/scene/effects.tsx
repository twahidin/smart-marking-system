import type { CSSProperties } from "react";

type At = { left: string; top: string; delay?: number };
const at = ({ left, top, delay }: At, extra: CSSProperties = {}): CSSProperties => ({ left, top, animationDelay: delay ? `${delay}s` : undefined, ...extra });
const fx = (cls: string, style: CSSProperties, children?: React.ReactNode) => <div className={`fx ${cls}`} style={style} aria-hidden="true" data-testid="fx">{children}</div>;

/** A warm pulsing light: a lit doorway, a lamp, a screen. `size` is a percentage of the painting's width. */
export const Glow = (p: At & { size?: string }) => fx("fx-glow", at(p, { width: p.size ?? "12%" }));
export const Flag = (p: At) => fx("fx-flag", at(p));
/** Three bobbing dots: someone is thinking or writing. */
export const Dots = (p: At) => fx("fx-dots", at(p), <><i /><i /><i /></>);
/** `still` keeps the paper hidden until a cue moves it (the marking desk); without it the paper lands on its own every few seconds. */
export const Paper = (p: At & { still?: boolean }) => fx(`fx-paper${p.still ? " fx-still" : ""}`, at(p));
export const Stamp = (p: At & { text: string }) => fx("fx-stamp", at(p), p.text);
export const Tick = (p: At) => <svg className="fx fx-tick" style={at(p)} viewBox="0 0 24 24" aria-hidden="true" data-testid="fx"><path d="M4 13l5 5L20 7" /></svg>;
export const Book = (p: At & { color?: string }) => fx("fx-book", at(p, { background: p.color }));
export const Star = (p: At) => fx("fx-star", at(p));
