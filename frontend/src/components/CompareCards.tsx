import { ParsedReport } from "@/types";
import { Panel } from "./Panel";
import { Bar } from "./Bar";
import { getPredictionBlock, methodDisplayName } from "@/lib/utils";

interface Item {
  mode: string;
  report: ParsedReport | null;
}

export function CompareCards({ items }: { items: Item[] }) {
  const cleaned = items.filter((it) => it.report);
  if (cleaned.length === 0) return null;
  return (
    <Panel
      title="Model Comparison"
      subtitle="All three reasoning modes ran on the same matchup so you can see where they agree and where they don't."
    >
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        {cleaned.map(({ mode, report }) => {
          const { home, away, confidence } = getPredictionBlock(report!);
          const winner = home >= away ? "Home" : "Away";
          const top = Math.max(home, away);
          const conf = (confidence ?? "medium").toLowerCase();
          const confValue = conf === "high" ? 0.85 : conf === "medium" ? 0.6 : 0.35;

          return (
            <div
              key={mode}
              className="rounded-xl border border-white/[0.06] bg-bg-panel2/40 p-4"
            >
              <div className="flex items-center justify-between">
                <h4 className="font-display text-sm font-semibold text-slate-100">
                  {methodDisplayName(mode)}
                </h4>
                <span className="label capitalize">{conf}</span>
              </div>
              <div className="mt-3 flex items-baseline gap-2">
                <span className="font-display text-3xl font-bold text-court-glow">
                  {Math.round(top * 100)}%
                </span>
                <span className="text-xs text-slate-500">
                  · {winner} side
                </span>
              </div>

              <div className="mt-4 space-y-3">
                <Row label="Home" value={home} tone="win" />
                <Row label="Away" value={away} tone="loss" />
                <Row label="Confidence" value={confValue} tone="court" />
              </div>

              <div className="mt-3 text-xs text-slate-500">
                Gap: <strong className="text-slate-300">{Math.round(Math.abs(home - away) * 100)}%</strong>
              </div>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}

function Row({ label, value, tone }: { label: string; value: number; tone: "win" | "loss" | "court" }) {
  return (
    <div>
      <div className="flex items-center justify-between text-xs text-slate-400">
        <span>{label}</span>
        <span className="font-mono text-slate-200">{Math.round(value * 100)}%</span>
      </div>
      <Bar value={value} tone={tone} className="mt-1.5" />
    </div>
  );
}
