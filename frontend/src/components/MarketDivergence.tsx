import { MarketConsensus, ParsedReport } from "@/types";
import { Panel } from "./Panel";
import { getPredictionBlock } from "@/lib/utils";
import { AlertCircle, CheckCircle2 } from "lucide-react";

interface Props {
  report: ParsedReport;
  consensus: MarketConsensus | undefined;
  homeTeam: string;
  awayTeam: string;
}

export function MarketDivergence({ report, consensus, homeTeam, awayTeam }: Props) {
  if (!consensus?.available) return null;

  const { home: agentHome } = getPredictionBlock(report);
  const marketHome = consensus.market_home_prob ?? 0.5;
  const divergence = Math.abs(agentHome - marketHome);
  const direction = agentHome > marketHome ? "higher" : "lower";

  const flagged = divergence >= 0.05;

  return (
    <Panel
      title="Market Comparison"
      subtitle={`Bookmakers sampled: ${consensus.books_sampled ?? 0}`}
    >
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Cell label={`${homeTeam} · Agent`} value={agentHome} tone="court" />
        <Cell label={`${homeTeam} · Market`} value={marketHome} tone="default" />
        <Cell
          label="Divergence"
          value={agentHome - marketHome}
          tone={flagged ? (agentHome > marketHome ? "win" : "loss") : "default"}
          signed
        />
      </div>

      <div
        className={`mt-4 flex items-start gap-3 rounded-xl border p-4 text-sm ${
          flagged
            ? "border-accent/30 bg-accent/5 text-accent-glow"
            : "border-win/25 bg-win/5 text-win"
        }`}
      >
        {flagged ? (
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
        ) : (
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
        )}
        <span>
          {flagged ? (
            <>
              <strong>Divergence flagged ({Math.round(divergence * 100)}%):</strong> the agent's
              home win probability is {Math.round(divergence * 100)}% {direction} than the
              market consensus. May indicate an edge or a model blind spot worth inspecting.
            </>
          ) : (
            <>
              Agent and market are aligned (divergence {Math.round(divergence * 100)}% &lt; 5%
              threshold).
            </>
          )}
        </span>
      </div>
      <p className="sr-only">Away team is {awayTeam}</p>
    </Panel>
  );
}

function Cell({
  label,
  value,
  tone,
  signed,
}: {
  label: string;
  value: number;
  tone: "win" | "loss" | "court" | "default";
  signed?: boolean;
}) {
  const colorMap = {
    win: "text-win",
    loss: "text-loss",
    court: "text-court-glow",
    default: "text-slate-100",
  }[tone];
  const text = signed
    ? `${value >= 0 ? "+" : ""}${(value * 100).toFixed(0)}%`
    : `${(value * 100).toFixed(0)}%`;
  return (
    <div className="rounded-xl border border-white/[0.06] bg-bg-panel2/40 px-4 py-3">
      <div className="label">{label}</div>
      <div className={`mt-1 font-display text-2xl font-bold ${colorMap}`}>{text}</div>
    </div>
  );
}
