import { Panel } from "./Panel";
import { Bar } from "./Bar";

interface AgentRow {
  agent: string;
  prediction?: { home_win_prob?: number; away_win_prob?: number };
  confidence?: string;
  reasoning?: string;
}

interface Props {
  agents: Record<string, AgentRow>;
}

const NAME_MAP: Record<string, string> = {
  stats_agent: "Stats & Metrics",
  matchup_agent: "Matchup & Context",
  market_agent: "Market & Odds",
};

export function AgentBreakdown({ agents }: Props) {
  const entries = Object.entries(agents ?? {});
  if (entries.length === 0) return null;

  return (
    <Panel
      title="Agent Breakdown"
      subtitle="Each agent ran with a different toolset and produced an independent forecast"
    >
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        {entries.map(([key, row]) => (
          <AgentCard key={key} agentKey={key} row={row} />
        ))}
      </div>
    </Panel>
  );
}

function AgentCard({ agentKey, row }: { agentKey: string; row: AgentRow }) {
  const home = row.prediction?.home_win_prob ?? 0.5;
  const away = row.prediction?.away_win_prob ?? 0.5;
  const conf = (row.confidence ?? "medium").toLowerCase();
  const confValue = conf === "high" ? 0.85 : conf === "medium" ? 0.6 : 0.35;
  const accent = agentKey === "stats_agent"
    ? "text-court-glow"
    : agentKey === "matchup_agent"
    ? "text-accent-glow"
    : "text-win";

  return (
    <div className="rounded-xl border border-white/[0.06] bg-bg-panel2/40 p-4">
      <div className="flex items-center justify-between">
        <h4 className={`font-display text-sm font-semibold ${accent}`}>
          {NAME_MAP[agentKey] ?? agentKey}
        </h4>
        <span className="label capitalize">{conf}</span>
      </div>

      <div className="mt-3 space-y-3">
        <Row label="Home" value={home} tone="win" />
        <Row label="Away" value={away} tone="loss" />
        <Row label="Confidence" value={confValue} tone="court" />
      </div>
    </div>
  );
}

function Row({ label, value, tone }: { label: string; value: number; tone: "win" | "loss" | "court" }) {
  return (
    <div>
      <div className="flex items-center justify-between text-xs text-slate-400">
        <span>{label}</span>
        <span className="font-mono text-slate-200">
          {Math.round(value * 100)}%
        </span>
      </div>
      <Bar value={value} tone={tone} className="mt-1.5" />
    </div>
  );
}
