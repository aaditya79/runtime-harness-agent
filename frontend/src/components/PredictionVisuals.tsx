import { ParsedReport } from "@/types";
import { Panel } from "./Panel";
import { ProbabilityRing } from "./ProbabilityRing";
import { Bar } from "./Bar";
import { getPredictionBlock } from "@/lib/utils";

interface Props {
  report: ParsedReport;
  homeTeam: string;
  awayTeam: string;
}

export function PredictionVisuals({ report, homeTeam, awayTeam }: Props) {
  const { home, away, confidence } = getPredictionBlock(report);
  const gap = Math.abs(home - away);
  const conf = confidence.toLowerCase();
  const confScore = conf === "high" ? 0.85 : conf === "medium" ? 0.6 : 0.35;

  const gapNarrative =
    gap >= 0.3
      ? "Large separation. The model sees one side as a clear favorite."
      : gap >= 0.15
      ? "Moderate edge. There's a real lean, but it's not overwhelming."
      : "Close matchup. Not much separation between the teams.";

  const confNarrative =
    conf === "high"
      ? "The model sees a strong edge supported by multiple signals."
      : conf === "low"
      ? "The model sees meaningful uncertainty or conflicting signals."
      : "The model sees a real edge, but not a decisive one.";

  return (
    <Panel title="Win Probability" subtitle="Forecast surface · home vs away">
      <div className="grid grid-cols-1 items-center gap-8 md:grid-cols-[1fr_1fr_1.4fr]">
        <div className="flex justify-center">
          <ProbabilityRing pct={away} label={awayTeam} sublabel="Away" tone="loss" />
        </div>
        <div className="flex justify-center">
          <ProbabilityRing pct={home} label={homeTeam} sublabel="Home" tone="win" />
        </div>

        <div className="space-y-4">
          <div className="rounded-xl border border-white/[0.06] bg-bg-panel2/50 p-4">
            <div className="label">Confidence</div>
            <div className="mt-1 flex items-baseline justify-between">
              <span className="font-display text-2xl font-bold capitalize text-court-glow">
                {confidence}
              </span>
              <span className="text-xs text-slate-500">{Math.round(confScore * 100)}/100</span>
            </div>
            <Bar value={confScore} tone="court" className="mt-2" />
            <p className="mt-3 text-xs text-slate-400">{confNarrative}</p>
          </div>

          <div className="rounded-xl border border-white/[0.06] bg-bg-panel2/50 p-4">
            <div className="label">Probability Gap</div>
            <div className="mt-1 flex items-baseline justify-between">
              <span className="font-display text-2xl font-bold text-accent-glow">
                {Math.round(gap * 100)}%
              </span>
              <span className="text-xs text-slate-500">spread</span>
            </div>
            <Bar value={Math.min(1, gap)} tone="accent" className="mt-2" />
            <p className="mt-3 text-xs text-slate-400">{gapNarrative}</p>
          </div>
        </div>
      </div>
    </Panel>
  );
}
