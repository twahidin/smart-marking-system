import type { ButtonHTMLAttributes, ReactNode } from "react";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost"; size?: "sm" | "md" | "lg"; wide?: boolean; keyHint?: string; icon?: ReactNode;
};

export function Button({ variant = "secondary", size = "md", wide, keyHint, icon, className = "", children, ...rest }: Props) {
  const cls = ["btn", `btn-${variant}`, size === "lg" ? "btn-lg" : size === "sm" ? "btn-sm" : "", wide ? "btn-wide" : "", className].join(" ");
  return (
    <button className={cls} {...rest}>
      {icon}{children}{keyHint && <span className="key">{keyHint}</span>}
    </button>
  );
}
