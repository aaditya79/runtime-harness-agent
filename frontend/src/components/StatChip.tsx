import { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function StatChip({
  label,
  value,
  hint,
  tone = "default",
  className,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: "default" | "win" | "loss" | "court" | "warn";
  className?: string;
}) {
  const toneClass = {
    default: "text-slate-100",
    win: "text-win",
    loss: "text-loss",
    court: "text-court-glow",
    warn: "text-warn",
  }[tone];

  return (
    <div className={cn("stat-card", className)}>
      <span className="label">{label}</span>
      <span className={cn("font-display text-base font-semibold", toneClass)}>{value}</span>
      {hint && <span className="text-[11px] text-slate-500">{hint}</span>}
    </div>
  );
}
