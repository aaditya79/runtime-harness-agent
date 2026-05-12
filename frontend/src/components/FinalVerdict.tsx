import { ParsedReport } from "@/types";
import { getPredictionBlock } from "@/lib/utils";
import { Trophy } from "lucide-react";

interface Props {
  report: ParsedReport;
  homeTeam: string;
  awayTeam: string;
}

export function FinalVerdict({ report, homeTeam, awayTeam }: Props) {
  const { home, away, confidence } = getPredictionBlock(report);
  const winner = home >= away ? homeTeam : awayTeam;
  const gap = Math.abs(home - away);
  const summary = (report.value_assessment || report.reasoning || "").trim();
  const trimmed =
    summary.length > 280 ? summary.slice(0, 280).split(/\s+/).slice(0, -1).join(" ") + "…" : summary;

  return (
    <div className="relative overflow-hidden rounded-2xl border border-accent/20 bg-gradient-to-br from-accent/15 via-court/10 to-transparent p-6 shadow-card">
      <div className="pointer-events-none absolute -right-10 -top-10 h-40 w-40 rounded-full bg-accent/30 blur-3xl" />
      <div className="pointer-events-none absolute -left-10 -bottom-10 h-44 w-44 rounded-full bg-court/30 blur-3xl" />

      <div className="relative flex items-start gap-4">
        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-accent/30 bg-accent/10 text-accent shadow-ember">
          <Trophy className="h-6 w-6" />
        </div>
        <div className="flex-1">
          <div className="label text-accent">Final Prediction</div>
          <h3 className="mt-1 font-display text-2xl font-bold tracking-tight text-slate-50">
            {winner} projected to win
          </h3>
          <div className="mt-1 flex flex-wrap items-center gap-3 text-sm text-slate-300">
            <span>Confidence: <strong className="capitalize text-slate-100">{confidence}</strong></span>
            <span className="text-slate-500">·</span>
            <span>Gap: <strong className="text-slate-100">{Math.round(gap * 100)}%</strong></span>
          </div>
          {trimmed && (
            <p className="mt-3 max-w-3xl text-sm leading-relaxed text-slate-300">{trimmed}</p>
          )}
        </div>
      </div>
    </div>
  );
}
