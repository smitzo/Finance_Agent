import type { HTMLAttributes } from "react";

type BadgeTone = "neutral" | "good" | "warn" | "danger" | "info";

const tones: Record<BadgeTone, string> = {
  neutral: "bg-slate-100 text-slate-700 dark:bg-white/10 dark:text-zinc-200",
  good: "bg-emerald-100 text-emerald-700 dark:bg-emerald-400/15 dark:text-emerald-200",
  warn: "bg-amber-100 text-amber-800 dark:bg-amber-400/15 dark:text-amber-200",
  danger: "bg-rose-100 text-rose-700 dark:bg-rose-400/15 dark:text-rose-200",
  info: "bg-sky-100 text-sky-700 dark:bg-sky-400/15 dark:text-sky-200",
};

type BadgeProps = HTMLAttributes<HTMLSpanElement> & {
  tone?: BadgeTone;
};

export function Badge({ className = "", tone = "neutral", ...props }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ${tones[tone]} ${className}`}
      {...props}
    />
  );
}
