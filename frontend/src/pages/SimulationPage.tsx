import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { AlertTriangle, ArrowRight, Database, Info, RotateCcw } from "lucide-react";
import { api } from "@/lib/api";
import { Panel } from "@/components/Panel";
import { StatChip } from "@/components/StatChip";
import { ChartTooltip } from "@/components/ChartTooltip";
import { methodDisplayName } from "@/lib/utils";
import type { RoiResponse } from "@/types";

const COLORS: Record<string, string> = {
  multi_agent_debate: "#ff8c61",
  single_agent: "#60a5fa",
  chain_of_thought: "#00d4a4",
};

export default function SimulationPage() {
  const [method, setMethod] = useState("All");
  const [edge, setEdge] = useState(0.05);
  const [side, setSide] = useState("Both");
  const [minConfidence, setMinConfidence] = useState(0.5);

  const sim = useQuery({
    queryKey: ["sim", method, edge, side, minConfidence],
    queryFn: () =>
      api.simulateRoi({
        method,
        edge_threshold: edge,
        side_filter: side,
        min_confidence: minConfidence,
      }),
  });

  const summary = sim.data?.summary ?? [];
  const bets = sim.data?.bets ?? [];
  const available = sim.data?.available ?? false;

  return (
    <div className="space-y-6">
      <Hero />

      <Panel
        title="Simulation Controls"
        subtitle="Bet only when model probability exceeds market by ≥ edge. Flat 1-unit stake."
      >
        <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
          <Field label="Method">
            <select className="input" value={method} onChange={(e) => setMethod(e.target.value)}>
              <option value="All">All Methods</option>
              <option value="multi_agent_debate">Multi-Agent Debate</option>
              <option value="single_agent">Single Agent</option>
              <option value="chain_of_thought">Chain-of-Thought</option>
            </select>
          </Field>
          <Field label={`Edge Threshold · ${(edge * 100).toFixed(0)}%`}>
            <input
              type="range"
              min={0}
              max={0.2}
              step={0.01}
              value={edge}
              onChange={(e) => setEdge(parseFloat(e.target.value))}
              className="w-full accent-[color:var(--tw-color-accent,#ff6b35)]"
            />
          </Field>
          <Field label="Allowed Side">
            <select className="input" value={side} onChange={(e) => setSide(e.target.value)}>
              <option value="Both">Both</option>
              <option value="Home Only">Home Only</option>
              <option value="Away Only">Away Only</option>
            </select>
          </Field>
          <Field label={`Min Confidence · ${(minConfidence * 100).toFixed(0)}%`}>
            <input
              type="range"
              min={0.5}
              max={0.95}
              step={0.01}
              value={minConfidence}
              onChange={(e) => setMinConfidence(parseFloat(e.target.value))}
              className="w-full accent-[color:var(--tw-color-accent,#ff6b35)]"
            />
          </Field>
        </div>
      </Panel>

      {sim.data && (sim.data.summary?.length ?? 0) === 0 && (
        <DiagnosticPanel
          response={sim.data}
          onRelax={() => {
            setEdge(0);
            setMinConfidence(0.5);
            setSide("Both");
          }}
        />
      )}

      {available && summary.length > 0 && (
        <>
          <Panel title="Overview">
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <StatChip
                label="Best ROI"
                value={`${(bestBy(summary, "roi", true).roi * 100).toFixed(1)}%`}
                hint={methodDisplayName(bestBy(summary, "roi", true).method)}
                tone={bestBy(summary, "roi", true).roi > 0 ? "win" : "loss"}
              />
              <StatChip
                label="Most Units Won"
                value={bestBy(summary, "total_units", true).total_units.toFixed(2)}
                hint={methodDisplayName(bestBy(summary, "total_units", true).method)}
                tone={bestBy(summary, "total_units", true).total_units > 0 ? "win" : "loss"}
              />
              <StatChip
                label="Best Win Rate"
                value={`${(bestBy(summary, "win_rate", true).win_rate * 100).toFixed(1)}%`}
                hint={methodDisplayName(bestBy(summary, "win_rate", true).method)}
                tone="warn"
              />
              <StatChip
                label="Most Bets"
                value={String(bestBy(summary, "n_bets", true).n_bets)}
                hint={methodDisplayName(bestBy(summary, "n_bets", true).method)}
                tone="court"
              />
            </div>
          </Panel>

          <Panel title="Method-Level Summary">
            <div className="overflow-x-auto rounded-xl border border-white/[0.06]">
              <table className="w-full text-left text-sm">
                <thead className="bg-white/[0.02] text-[11px] uppercase tracking-wider text-slate-400">
                  <tr>
                    <th className="px-3 py-2">Method</th>
                    <th className="px-3 py-2 text-right">Bets</th>
                    <th className="px-3 py-2 text-right">Win Rate</th>
                    <th className="px-3 py-2 text-right">Total Units</th>
                    <th className="px-3 py-2 text-right">ROI</th>
                    <th className="px-3 py-2 text-right">Avg Edge</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/[0.04]">
                  {[...summary]
                    .sort((a, b) => b.roi - a.roi)
                    .map((r) => (
                      <tr key={r.method} className="hover:bg-white/[0.02]">
                        <td className="px-3 py-2 font-medium text-slate-100">
                          {methodDisplayName(r.method)}
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-slate-200">
                          {r.n_bets}
                        </td>
                        <td className="px-3 py-2 text-right font-mono">
                          {(r.win_rate * 100).toFixed(1)}%
                        </td>
                        <td
                          className={`px-3 py-2 text-right font-mono ${
                            r.total_units >= 0 ? "text-win" : "text-loss"
                          }`}
                        >
                          {r.total_units.toFixed(2)}
                        </td>
                        <td
                          className={`px-3 py-2 text-right font-mono font-semibold ${
                            r.roi >= 0 ? "text-win" : "text-loss"
                          }`}
                        >
                          {(r.roi * 100).toFixed(2)}%
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-slate-400">
                          {(r.avg_edge * 100).toFixed(2)}%
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </Panel>

          <Panel title="ROI by Method">
            <ResponsiveContainer width="100%" height={300}>
              <BarChart
                data={summary.map((r) => ({
                  method: methodDisplayName(r.method),
                  raw: r.method,
                  roi: r.roi,
                }))}
              >
                <CartesianGrid stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="method" stroke="rgba(255,255,255,0.5)" />
                <YAxis stroke="rgba(255,255,255,0.5)" tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} />
                <ReferenceLine y={0} stroke="rgba(255,255,255,0.3)" strokeDasharray="3 3" />
                <Tooltip
                  cursor={{ fill: "rgba(255,255,255,0.04)" }}
                  content={
                    <ChartTooltip
                      labelFormatter={(v: any) => `Method: ${v}`}
                      valueFormatter={(v: any) => {
                        if (typeof v !== "number") return [String(v), "ROI"];
                        const sign = v >= 0 ? "+" : "";
                        return [`${sign}${(v * 100).toFixed(2)}%`, "ROI"];
                      }}
                    />
                  }
                />
                <Bar dataKey="roi" radius={[6, 6, 0, 0]}>
                  {summary.map((r, i) => (
                    <Cell key={i} fill={r.roi >= 0 ? "#00d4a4" : "#ff5470"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </Panel>

          {bets.length > 0 && (
            <Panel
              title="Cumulative Units"
              subtitle="Bankroll path under flat 1-unit staking, by method."
            >
              <ResponsiveContainer width="100%" height={340}>
                <LineChart>
                  <CartesianGrid stroke="rgba(255,255,255,0.05)" />
                  <XAxis dataKey="date" stroke="rgba(255,255,255,0.5)" />
                  <YAxis stroke="rgba(255,255,255,0.5)" />
                  <Tooltip
                    cursor={{ stroke: "rgba(255,255,255,0.18)", strokeDasharray: "3 3" }}
                    content={
                      <ChartTooltip
                        labelFormatter={(v: any) => `Date: ${v}`}
                        valueFormatter={(v: any, name?: string) => {
                          if (typeof v !== "number") return [String(v), name ?? "Units"];
                          const sign = v >= 0 ? "+" : "";
                          return [`${sign}${v.toFixed(2)} u`, name ?? "Units"];
                        }}
                      />
                    }
                  />
                  <Legend />
                  {Object.keys(COLORS).map((m) => {
                    const data = bets
                      .filter((b) => b.method === m)
                      .map((b) => ({ date: b.date, units: b.cum_units }));
                    if (data.length === 0) return null;
                    return (
                      <Line
                        key={m}
                        data={data}
                        type="monotone"
                        dataKey="units"
                        stroke={COLORS[m]}
                        strokeWidth={2.4}
                        dot={false}
                        name={methodDisplayName(m)}
                      />
                    );
                  })}
                </LineChart>
              </ResponsiveContainer>
            </Panel>
          )}

          {bets.length > 0 && (
            <Panel title="Simulated Bets" subtitle="The individual bets that passed the filters.">
              <div className="overflow-x-auto rounded-xl border border-white/[0.06]">
                <table className="w-full text-left text-sm">
                  <thead className="bg-white/[0.02] text-[11px] uppercase tracking-wider text-slate-400">
                    <tr>
                      <th className="px-3 py-2">Date</th>
                      <th className="px-3 py-2">Matchup</th>
                      <th className="px-3 py-2">Method</th>
                      <th className="px-3 py-2">Side</th>
                      <th className="px-3 py-2 text-right">Edge</th>
                      <th className="px-3 py-2 text-right">Conf</th>
                      <th className="px-3 py-2 text-right">Won</th>
                      <th className="px-3 py-2 text-right">Units</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/[0.04]">
                    {bets.slice(0, 200).map((b, i) => (
                      <tr key={i} className="hover:bg-white/[0.02]">
                        <td className="px-3 py-2 font-mono text-xs text-slate-400">{b.date}</td>
                        <td className="px-3 py-2 text-slate-200">
                          {b.away_team} @ {b.home_team}
                        </td>
                        <td className="px-3 py-2 text-slate-300">{methodDisplayName(b.method)}</td>
                        <td className="px-3 py-2 text-slate-300">{b.side_bet}</td>
                        <td className="px-3 py-2 text-right font-mono">
                          {(b.edge * 100).toFixed(1)}%
                        </td>
                        <td className="px-3 py-2 text-right font-mono">
                          {(b.model_confidence * 100).toFixed(0)}%
                        </td>
                        <td className="px-3 py-2 text-right">
                          <span
                            className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${
                              b.won
                                ? "border-win/30 bg-win/10 text-win"
                                : "border-loss/30 bg-loss/10 text-loss"
                            }`}
                          >
                            {b.won ? "Won" : "Lost"}
                          </span>
                        </td>
                        <td
                          className={`px-3 py-2 text-right font-mono ${
                            b.units >= 0 ? "text-win" : "text-loss"
                          }`}
                        >
                          {b.units.toFixed(2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
          )}
        </>
      )}
    </div>
  );
}

function DiagnosticPanel({
  response,
  onRelax,
}: {
  response: RoiResponse;
  onRelax: () => void;
}) {
  const reason = response.reason ?? (response.available ? "no_qualifying_bets" : "predictions_missing");
  const message = response.message ?? "";
  const diag = response.diagnostics ?? {};

  // Three classes of failure get different visual treatment + actions.
  const isDataIssue =
    reason === "predictions_missing" ||
    reason === "predictions_empty" ||
    reason === "market_columns_missing" ||
    reason === "market_data_missing";

  const isFilterIssue =
    reason === "no_qualifying_bets" || reason === "no_rows_after_method_filter";

  return (
    <Panel
      title={
        <span className="flex items-center gap-2">
          <AlertTriangle
            className={`h-4 w-4 ${isDataIssue ? "text-warn" : "text-court-glow"}`}
          />
          {isDataIssue ? "Setup needed" : "No qualifying bets"}
        </span>
      }
    >
      <p className="text-sm leading-relaxed text-slate-300">{message}</p>

      {Object.keys(diag).length > 0 && (
        <details className="mt-3 rounded-lg border border-white/[0.06] bg-bg-panel2/40 p-3 text-xs">
          <summary className="cursor-pointer text-slate-400">Diagnostics</summary>
          <ul className="mt-2 space-y-0.5 font-mono text-[11px] text-slate-500">
            {Object.entries(diag).map(([k, v]) => (
              <li key={k}>
                <span className="text-slate-400">{k}:</span> {String(v)}
              </li>
            ))}
          </ul>
        </details>
      )}

      {reason === "market_data_missing" && (
        <div className="mt-4 grid grid-cols-1 gap-2 text-xs sm:grid-cols-2">
          <div className="rounded-lg border border-warn/20 bg-warn/5 p-3">
            <div className="font-semibold uppercase tracking-wider text-warn">
              Step 1 · manual download
            </div>
            <p className="mt-1 text-slate-300">
              Save{" "}
              <span className="font-mono text-slate-100">data/kaggle_odds.csv</span> from{" "}
              <a
                href="https://www.kaggle.com/datasets/erichqiu/nba-odds-and-scores"
                target="_blank"
                rel="noreferrer"
                className="underline decoration-dotted underline-offset-2 hover:text-accent-glow"
              >
                kaggle.com/datasets/erichqiu/nba-odds-and-scores
              </a>
              .
            </p>
          </div>
          <div className="rounded-lg border border-court/20 bg-court/5 p-3">
            <div className="font-semibold uppercase tracking-wider text-court-glow">
              Step 2 · re-run pipelines
            </div>
            <p className="mt-1 text-slate-300">
              Run the <strong>Odds</strong> pipeline (writes{" "}
              <span className="font-mono">odds_historical.csv</span>), then run a fresh{" "}
              <strong>Backtest</strong>.
            </p>
          </div>
        </div>
      )}

      <div className="mt-4 flex flex-wrap gap-2">
        {(reason === "predictions_missing" ||
          reason === "predictions_empty" ||
          reason === "market_columns_missing") && (
          <Link to="/research" className="btn-primary">
            <ArrowRight className="h-4 w-4" />
            Open Research page
          </Link>
        )}
        {reason === "market_data_missing" && (
          <Link to="/data" className="btn-primary">
            <Database className="h-4 w-4" />
            Open Data pipelines
          </Link>
        )}
        {isFilterIssue && (
          <button type="button" className="btn-primary" onClick={onRelax}>
            <RotateCcw className="h-4 w-4" />
            Relax filters
          </button>
        )}
        <a
          href="/docs#/backtest"
          target="_blank"
          rel="noreferrer"
          className="btn-ghost"
        >
          <Info className="h-4 w-4" />
          API docs
        </a>
      </div>
    </Panel>
  );
}

function Hero() {
  return (
    <div className="relative overflow-hidden rounded-3xl border border-white/[0.06] bg-bg-panel/60 p-7">
      <div className="pointer-events-none absolute -right-12 -top-12 h-44 w-44 rounded-full bg-win/20 blur-3xl" />
      <span className="chip">Research extension</span>
      <h1 className="mt-3 text-balance font-display text-3xl font-bold tracking-tight text-slate-50 md:text-4xl">
        Simulated betting ROI
      </h1>
      <p className="mt-2 max-w-2xl text-sm text-slate-400">
        Flat-stake simulation against market consensus. A bet fires only when the model edge
        passes your threshold and the model's top-side confidence clears the floor.
      </p>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="label mb-1 inline-block">{label}</span>
      {children}
    </label>
  );
}

function bestBy<T extends Record<string, any>>(rows: T[], key: keyof T, higherBetter: boolean): T {
  return [...rows].sort((a, b) =>
    higherBetter ? (b[key] as number) - (a[key] as number) : (a[key] as number) - (b[key] as number),
  )[0];
}

