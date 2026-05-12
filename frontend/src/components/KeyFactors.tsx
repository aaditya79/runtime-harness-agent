import { KeyFactor } from "@/types";
import { Panel } from "./Panel";
import { cn, impactLabel, importanceWeight } from "@/lib/utils";
import { Minus, TrendingDown, TrendingUp, User } from "lucide-react";

const SOURCE_AGENT_LABEL: Record<string, string> = {
  stats_agent: "Stats Agent",
  matchup_agent: "Matchup Agent",
  market_agent: "Market Agent",
};

export function KeyFactors({ factors }: { factors: KeyFactor[] }) {
  if (!factors || factors.length === 0) return null;
  return (
    <Panel
      title="Key Factors"
      subtitle="Drivers behind the prediction · with directional impact, influence weight, and the underlying numeric edge"
    >
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {factors.map((f, i) => (
          <FactorCard key={i} factor={f} index={i} />
        ))}
      </div>
    </Panel>
  );
}

function FactorCard({ factor, index }: { factor: KeyFactor; index: number }) {
  const impactKey = (factor.impact || "neutral").toString().toLowerCase();
  const importance = (factor.importance || "medium").toString().toLowerCase();

  const tone = impactKey.includes("home")
    ? "win"
    : impactKey.includes("away")
    ? "loss"
    : "court";

  const Icon = tone === "win" ? TrendingUp : tone === "loss" ? TrendingDown : Minus;

  const colorMap = {
    win: {
      border: "border-win/25",
      bg: "bg-win/5",
      stripe: "bg-win",
      text: "text-win",
      chip: "bg-win/15 text-win border-win/30",
      bar: "bg-win",
      metricBg: "bg-win/10 border-win/25 text-win",
    },
    loss: {
      border: "border-loss/25",
      bg: "bg-loss/5",
      stripe: "bg-loss",
      text: "text-loss",
      chip: "bg-loss/15 text-loss border-loss/30",
      bar: "bg-loss",
      metricBg: "bg-loss/10 border-loss/25 text-loss",
    },
    court: {
      border: "border-court/25",
      bg: "bg-court/5",
      stripe: "bg-court",
      text: "text-court-glow",
      chip: "bg-court/15 text-court-glow border-court/30",
      bar: "bg-court",
      metricBg: "bg-court/10 border-court/25 text-court-glow",
    },
  }[tone];

  // Score: backend provides 0..100; fall back to importance bucket if absent.
  const score =
    typeof factor.influence_score === "number"
      ? Math.max(0, Math.min(100, Math.round(factor.influence_score)))
      : importanceWeight(importance);

  const importanceText =
    importance === "high"
      ? "High influence"
      : importance === "low"
      ? "Low influence"
      : "Medium influence";

  const sourceLabel = factor.source_agent
    ? SOURCE_AGENT_LABEL[factor.source_agent] ?? factor.source_agent
    : null;

  const hasMetric =
    typeof factor.metric_value === "string" && factor.metric_value.trim().length > 0;

  return (
    <div
      style={{ animationDelay: `${index * 60}ms` }}
      className={cn(
        "relative animate-fade-in-up overflow-hidden rounded-xl border p-4 pl-5",
        colorMap.border,
        colorMap.bg,
      )}
    >
      {/* Left edge accent stripe */}
      <span
        aria-hidden
        className={cn("absolute left-0 top-0 bottom-0 w-1", colorMap.stripe)}
      />

      <div className="flex items-start justify-between gap-3">
        <span
          className={cn(
            "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider",
            colorMap.chip,
          )}
        >
          <Icon className="h-3 w-3" />
          {impactLabel(impactKey)}
        </span>

        {hasMetric ? (
          <div
            className={cn(
              "flex flex-col items-end rounded-lg border px-2.5 py-1.5 text-right leading-tight",
              colorMap.metricBg,
            )}
            title={factor.metric_label ? `${factor.metric_label}` : undefined}
          >
            <span className="font-display text-base font-bold tabular-nums">
              {factor.metric_value}
            </span>
            {factor.metric_label && (
              <span className="text-[9px] font-semibold uppercase tracking-wider opacity-80">
                {factor.metric_label}
              </span>
            )}
          </div>
        ) : (
          <div className="flex flex-col items-end leading-tight">
            <span className={cn("font-display text-xl font-bold tabular-nums", colorMap.text)}>
              {score}
            </span>
            <span className="text-[9px] font-semibold uppercase tracking-wider text-slate-500">
              / 100
            </span>
          </div>
        )}
      </div>

      <p className="mt-3 text-sm font-medium leading-relaxed text-slate-100">
        {factor.factor}
      </p>

      {/* Influence bar */}
      <div className="mt-4">
        <div className="flex items-center justify-between text-[10px] font-semibold uppercase tracking-wider text-slate-500">
          <span>{importanceText}</span>
          <span className="font-mono text-slate-400">{score}/100</span>
        </div>
        <div className="mt-1.5 h-2 w-full overflow-hidden rounded-full bg-white/[0.06]">
          <div
            className={cn("h-full rounded-full", colorMap.bar)}
            style={{
              width: `${score}%`,
              transition: "width 0.8s cubic-bezier(0.4,0,0.2,1)",
              opacity: 0.85,
            }}
          />
        </div>
      </div>

      {sourceLabel && (
        <div className="mt-3 flex items-center gap-1.5 border-t border-white/[0.06] pt-2.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
          <User className="h-3 w-3" />
          Flagged by {sourceLabel}
        </div>
      )}
    </div>
  );
}
