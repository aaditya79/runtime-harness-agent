import { cn } from "@/lib/utils";

interface Props {
  pct: number; // 0..1
  label: string;
  sublabel?: string;
  size?: number;
  tone?: "win" | "loss" | "court";
}

export function ProbabilityRing({ pct, label, sublabel, size = 168, tone = "court" }: Props) {
  const safe = Math.max(0, Math.min(1, pct));
  const radius = (size - 18) / 2;
  const circ = 2 * Math.PI * radius;
  const offset = circ * (1 - safe);

  const colorMap = {
    win: { stroke: "#00d4a4", text: "text-win", glow: "drop-shadow(0 0 12px rgba(0,212,164,0.45))" },
    loss: { stroke: "#ff5470", text: "text-loss", glow: "drop-shadow(0 0 12px rgba(255,84,112,0.45))" },
    court: { stroke: "#60a5fa", text: "text-court-glow", glow: "drop-shadow(0 0 12px rgba(96,165,250,0.45))" },
  }[tone];

  return (
    <div className="flex flex-col items-center gap-2">
      <div
        className="relative"
        style={{ width: size, height: size, filter: colorMap.glow as any }}
      >
        <svg width={size} height={size} className="-rotate-90">
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            stroke="rgba(255,255,255,0.06)"
            strokeWidth={9}
            fill="none"
          />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            stroke={colorMap.stroke}
            strokeWidth={9}
            fill="none"
            strokeDasharray={circ}
            strokeDashoffset={offset}
            strokeLinecap="round"
            style={{ transition: "stroke-dashoffset 1s cubic-bezier(0.4, 0, 0.2, 1)" }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={cn("font-display text-3xl font-bold tracking-tight", colorMap.text)}>
            {Math.round(safe * 100)}%
          </span>
          {sublabel && (
            <span className="mt-1 text-[10px] uppercase tracking-[0.18em] text-slate-500">
              {sublabel}
            </span>
          )}
        </div>
      </div>
      <div className="text-center">
        <div className="text-sm font-semibold text-slate-100">{label}</div>
      </div>
    </div>
  );
}
