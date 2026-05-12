import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
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
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import { CheckCircle2, ChevronDown, Loader2, Play, Terminal, XCircle } from "lucide-react";
import { api } from "@/lib/api";
import { Panel } from "@/components/Panel";
import { StatChip } from "@/components/StatChip";
import { ChartTooltip } from "@/components/ChartTooltip";
import { cn, formatNumber, methodDisplayName } from "@/lib/utils";
import { useBacktestJob } from "@/hooks/useBacktestJob";
import type { BacktestSummaryRow, CalibrationRow, PredictionRow } from "@/types";

const NUMERIC_METRICS = [
  "accuracy",
  "precision",
  "recall",
  "f1",
  "log_loss",
  "brier_score",
  "mae_prob",
  "avg_confidence",
  "avg_gap",
  "ece",
] as const;

type Metric = (typeof NUMERIC_METRICS)[number];

const COLORS: Record<string, string> = {
  multi_agent_debate: "#ff8c61",
  single_agent: "#60a5fa",
  chain_of_thought: "#00d4a4",
};

export default function ResearchPage() {
  const qc = useQueryClient();

  const summary = useQuery({ queryKey: ["bt-summary"], queryFn: api.backtestSummary });
  const predictions = useQuery({ queryKey: ["bt-preds"], queryFn: api.backtestPredictions });
  const calibration = useQuery({ queryKey: ["bt-cal"], queryFn: api.backtestCalibration });
  const ablations = useQuery({ queryKey: ["bt-ablations"], queryFn: api.backtestAblations });

  const summaryRows = (summary.data?.summary ?? []) as BacktestSummaryRow[];
  const meta = summary.data?.metadata ?? {};
  const predRows = predictions.data ?? [];
  const calRows = calibration.data ?? [];

  const [nGames, setNGames] = useState(25);
  const [season, setSeason] = useState("2025-26");
  const [minHist, setMinHist] = useState(10);

  const job = useBacktestJob(() => {
    qc.invalidateQueries({ queryKey: ["bt-summary"] });
    qc.invalidateQueries({ queryKey: ["bt-preds"] });
    qc.invalidateQueries({ queryKey: ["bt-cal"] });
    qc.invalidateQueries({ queryKey: ["bt-ablations"] });
  });

  const runBacktest = () => {
    job.start({ n_games: nGames, season, min_history: minHist });
  };

  const availableMetrics = useMemo(
    () => NUMERIC_METRICS.filter((m) => summaryRows.some((r) => typeof (r as any)[m] === "number")),
    [summaryRows],
  );

  const [primaryMetric, setPrimaryMetric] = useState<Metric>("brier_score");
  const [chartMetric, setChartMetric] = useState<Metric>("accuracy");

  const empty = summaryRows.length === 0;

  return (
    <div className="space-y-6">
      <Hero />

      <Panel title="Backtest Controls" subtitle="Run a fresh sweep against historical data.">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
          <Field label="Number of Games">
            <input
              className="input"
              type="number"
              min={5}
              max={150}
              value={nGames}
              onChange={(e) => setNGames(parseInt(e.target.value || "0", 10))}
            />
          </Field>
          <Field label="Season">
            <select
              className="input"
              value={season}
              onChange={(e) => setSeason(e.target.value)}
            >
              {["2025-26", "2024-25", "2023-24", "2022-23", "All"].map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Min Prior Games">
            <input
              className="input"
              type="number"
              min={5}
              max={20}
              value={minHist}
              onChange={(e) => setMinHist(parseInt(e.target.value || "0", 10))}
            />
          </Field>
          <div className="flex items-end">
            <button
              type="button"
              className="btn-primary w-full"
              onClick={runBacktest}
              disabled={job.status === "running"}
            >
              {job.status === "running" ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Play className="h-4 w-4" />
              )}
              {job.status === "running" ? "Running…" : "Run / Refresh Backtest"}
            </button>
          </div>
        </div>

        {job.error && (
          <p className="mt-3 text-xs text-loss">{job.error}</p>
        )}
      </Panel>

      {(job.status === "running" || job.output.length > 0) && (
        <BacktestLogPane
          status={job.status}
          output={job.output}
          startedAt={job.startedAt}
          finishedAt={job.finishedAt}
          exitCode={job.exitCode}
        />
      )}

      {meta && Object.keys(meta).length > 0 && <RunHealth meta={meta} />}

      {empty ? (
        <Panel>
          <div className="flex flex-col items-center justify-center gap-2 py-10 text-center text-sm text-slate-400">
            <span className="font-display text-base font-semibold text-slate-100">
              No backtest results yet
            </span>
            Run a backtest from the controls above to populate this page.
          </div>
        </Panel>
      ) : (
        <>
          <Panel
            title="Headline Metrics"
            subtitle="Higher is better for accuracy, precision, recall, F1. Lower is better for log loss, Brier, MAE, ECE."
          >
            <div className="mb-4 flex items-center gap-2">
              <span className="label">Primary metric</span>
              <select
                className="input max-w-xs"
                value={primaryMetric}
                onChange={(e) => setPrimaryMetric(e.target.value as Metric)}
              >
                {availableMetrics.map((m) => (
                  <option key={m} value={m}>
                    {prettyMetric(m)}
                  </option>
                ))}
              </select>
            </div>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <BestMetric rows={summaryRows} metric={primaryMetric} />
              <BestMetric rows={summaryRows} metric="accuracy" />
              <BestMetric rows={summaryRows} metric="log_loss" />
              <BestMetric rows={summaryRows} metric="ece" />
            </div>

            <div className="mt-6 overflow-x-auto rounded-xl border border-white/[0.06]">
              <table className="w-full text-left text-sm">
                <thead className="bg-white/[0.02] text-[11px] uppercase tracking-wider text-slate-400">
                  <tr>
                    <th className="px-3 py-2">Method</th>
                    {availableMetrics.map((m) => (
                      <th key={m} className="px-3 py-2 text-right">
                        {prettyMetric(m)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/[0.04]">
                  {summaryRows.map((r) => (
                    <tr key={r.method} className="hover:bg-white/[0.02]">
                      <td className="px-3 py-2 font-medium text-slate-100">
                        {methodDisplayName(r.method)}
                      </td>
                      {availableMetrics.map((m) => (
                        <td key={m} className="px-3 py-2 text-right font-mono text-slate-300">
                          {fmt(r[m as keyof BacktestSummaryRow] as number, m)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          <Panel
            title="Metric Comparison"
            subtitle="Visual head-to-head between methods on a single metric."
            action={
              <select
                className="input max-w-xs"
                value={chartMetric}
                onChange={(e) => setChartMetric(e.target.value as Metric)}
              >
                {availableMetrics.map((m) => (
                  <option key={m} value={m}>
                    {prettyMetric(m)}
                  </option>
                ))}
              </select>
            }
          >
            <ResponsiveContainer width="100%" height={320}>
              <BarChart
                data={summaryRows.map((r) => ({
                  method: methodDisplayName(r.method),
                  raw: r.method,
                  value: r[chartMetric as keyof BacktestSummaryRow] as number,
                }))}
              >
                <CartesianGrid stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="method" stroke="rgba(255,255,255,0.5)" />
                <YAxis stroke="rgba(255,255,255,0.5)" />
                <Tooltip
                  cursor={{ fill: "rgba(255,255,255,0.04)" }}
                  content={
                    <ChartTooltip
                      valueFormatter={(v: any) =>
                        typeof v === "number" ? fmt(v, chartMetric) : String(v)
                      }
                    />
                  }
                />
                <Bar dataKey="value" radius={[6, 6, 0, 0]}>
                  {summaryRows.map((r, i) => (
                    <Cell key={i} fill={COLORS[r.method] ?? "#60a5fa"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </Panel>

          {calRows.length > 0 && (
            <Panel
              title="Calibration"
              subtitle="Below the diagonal = overconfident. Above = underconfident."
            >
              <ResponsiveContainer width="100%" height={360}>
                <LineChart>
                  <CartesianGrid stroke="rgba(255,255,255,0.05)" />
                  <XAxis
                    type="number"
                    dataKey="x"
                    domain={[0, 1]}
                    stroke="rgba(255,255,255,0.5)"
                    tickFormatter={(v) => `${Math.round(v * 100)}%`}
                  />
                  <YAxis
                    type="number"
                    dataKey="y"
                    domain={[0, 1]}
                    stroke="rgba(255,255,255,0.5)"
                    tickFormatter={(v) => `${Math.round(v * 100)}%`}
                  />
                  <Tooltip
                    cursor={{ stroke: "rgba(255,255,255,0.18)", strokeDasharray: "3 3" }}
                    content={
                      <ChartTooltip
                        labelFormatter={(v: any) =>
                          typeof v === "number"
                            ? `Predicted home win prob: ${Math.round(v * 100)}%`
                            : String(v)
                        }
                        valueFormatter={(v: any) =>
                          typeof v === "number" ? `${(v * 100).toFixed(1)}%` : String(v)
                        }
                      />
                    }
                  />
                  <Legend />
                  <ReferenceLine
                    segment={[
                      { x: 0, y: 0 },
                      { x: 1, y: 1 },
                    ]}
                    stroke="rgba(255,255,255,0.2)"
                    strokeDasharray="4 4"
                    ifOverflow="extendDomain"
                  />
                  {Object.keys(COLORS).map((method) => {
                    const data = calRows
                      .filter((r) => r.method === method)
                      .map((r: CalibrationRow) => ({
                        x: r.avg_pred_home_win_prob,
                        y: r.actual_home_win_rate,
                      }))
                      .sort((a, b) => a.x - b.x);
                    if (data.length === 0) return null;
                    return (
                      <Line
                        key={method}
                        data={data}
                        type="monotone"
                        dataKey="y"
                        stroke={COLORS[method]}
                        strokeWidth={2.4}
                        dot={{ r: 4 }}
                        name={methodDisplayName(method)}
                      />
                    );
                  })}
                </LineChart>
              </ResponsiveContainer>
            </Panel>
          )}

          {ablations.data && ablations.data.length > 0 && (
            <Panel
              title="Ablation Study (RQ3)"
              subtitle="Per-source Brier delta vs the CoT baseline. Larger positive delta means the source matters more."
            >
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={ablations.data}>
                  <CartesianGrid stroke="rgba(255,255,255,0.05)" />
                  <XAxis dataKey="source" stroke="rgba(255,255,255,0.5)" />
                  <YAxis stroke="rgba(255,255,255,0.5)" />
                  <Tooltip
                    cursor={{ fill: "rgba(255,255,255,0.04)" }}
                    content={
                      <ChartTooltip
                        labelFormatter={(v: any) => `Removed source: ${v}`}
                        valueFormatter={(v: any, name?: string) => {
                          if (typeof v !== "number") return [String(v), name ?? "Δ Brier"];
                          const sign = v >= 0 ? "+" : "";
                          return [`${sign}${v.toFixed(4)}`, "Δ Brier vs baseline"];
                        }}
                      />
                    }
                  />
                  <ReferenceLine y={0} stroke="rgba(255,255,255,0.3)" strokeDasharray="3 3" />
                  <Bar dataKey="brier_delta" radius={[6, 6, 0, 0]}>
                    {ablations.data.map((r, i) => (
                      <Cell key={i} fill={r.brier_delta > 0 ? "#ff5470" : "#00d4a4"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </Panel>
          )}

          <InfoDensity rows={predRows} />

          <PredictionTable rows={predRows} />
        </>
      )}
    </div>
  );
}

function Hero() {
  return (
    <div className="relative overflow-hidden rounded-3xl border border-white/[0.06] bg-bg-panel/60 p-7">
      <div className="pointer-events-none absolute -right-12 -top-12 h-44 w-44 rounded-full bg-court/30 blur-3xl" />
      <span className="chip">Research mode</span>
      <h1 className="mt-3 text-balance font-display text-3xl font-bold tracking-tight text-slate-50 md:text-4xl">
        Backtesting & calibration dashboard
      </h1>
      <p className="mt-2 max-w-2xl text-sm text-slate-400">
        Compare multi-agent debate, single-agent reasoning, and chain-of-thought baselines on
        historical NBA games. Calibration, info density (RQ1), and per-source ablation (RQ3) all
        live here.
      </p>
    </div>
  );
}

function RunHealth({ meta }: { meta: Record<string, any> }) {
  const skipped = meta.games_skipped ?? 0;
  const ok = !skipped;
  return (
    <Panel title="Run Health">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatChip label="Requested" value={String(meta.n_games_requested ?? "—")} />
        <StatChip label="Selected" value={String(meta.candidate_games_selected ?? "—")} />
        <StatChip
          label="Skipped"
          value={String(skipped)}
          tone={ok ? "win" : "loss"}
          hint={ok ? "All games completed" : "Insufficient history or failures"}
        />
        <StatChip label="Prediction Rows" value={String(meta.prediction_rows ?? "—")} />
      </div>
    </Panel>
  );
}

function BestMetric({
  rows,
  metric,
}: {
  rows: BacktestSummaryRow[];
  metric: Metric;
}) {
  const higherBetter = ["accuracy", "precision", "recall", "f1"].includes(metric);
  const sorted = [...rows].sort((a, b) =>
    higherBetter
      ? ((b[metric] as number) ?? -Infinity) - ((a[metric] as number) ?? -Infinity)
      : ((a[metric] as number) ?? Infinity) - ((b[metric] as number) ?? Infinity),
  );
  const best = sorted[0];
  return (
    <StatChip
      label={`Best ${prettyMetric(metric)}`}
      value={fmt(best?.[metric] as number, metric)}
      hint={best ? methodDisplayName(best.method) : ""}
      tone={higherBetter ? "win" : "court"}
    />
  );
}

function PredictionTable({ rows }: { rows: PredictionRow[] }) {
  const [methodFilter, setMethodFilter] = useState("All");
  const [correctness, setCorrectness] = useState("All");

  const methods = useMemo(
    () => Array.from(new Set(rows.map((r) => r.method))).filter(Boolean),
    [rows],
  );

  const filtered = useMemo(() => {
    let data = rows.slice();
    if (methodFilter !== "All") data = data.filter((r) => r.method === methodFilter);
    if (correctness === "Correct Only") data = data.filter((r) => r.correct === 1);
    if (correctness === "Incorrect Only") data = data.filter((r) => r.correct === 0);
    return data.slice(0, 100);
  }, [rows, methodFilter, correctness]);

  if (rows.length === 0) return null;

  return (
    <Panel
      title="Prediction Inspector"
      subtitle="Drill into individual game-level predictions."
    >
      <div className="mb-4 grid grid-cols-1 gap-3 md:grid-cols-2">
        <select
          className="input"
          value={methodFilter}
          onChange={(e) => setMethodFilter(e.target.value)}
        >
          <option value="All">All Methods</option>
          {methods.map((m) => (
            <option key={m} value={m}>
              {methodDisplayName(m)}
            </option>
          ))}
        </select>
        <select
          className="input"
          value={correctness}
          onChange={(e) => setCorrectness(e.target.value)}
        >
          <option>All</option>
          <option>Correct Only</option>
          <option>Incorrect Only</option>
        </select>
      </div>

      <div className="overflow-x-auto rounded-xl border border-white/[0.06]">
        <table className="w-full text-left text-sm">
          <thead className="bg-white/[0.02] text-[11px] uppercase tracking-wider text-slate-400">
            <tr>
              <th className="px-3 py-2">Date</th>
              <th className="px-3 py-2">Matchup</th>
              <th className="px-3 py-2">Method</th>
              <th className="px-3 py-2 text-right">Home %</th>
              <th className="px-3 py-2 text-right">Away %</th>
              <th className="px-3 py-2">Result</th>
              <th className="px-3 py-2">Conf</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/[0.04]">
            {filtered.map((r, i) => (
              <tr key={i} className="hover:bg-white/[0.02]">
                <td className="px-3 py-2 font-mono text-xs text-slate-400">{r.date}</td>
                <td className="px-3 py-2 text-slate-200">
                  {r.away_team} @ {r.home_team}
                </td>
                <td className="px-3 py-2 text-slate-300">{methodDisplayName(r.method)}</td>
                <td className="px-3 py-2 text-right font-mono">
                  {Math.round(r.home_win_prob * 100)}%
                </td>
                <td className="px-3 py-2 text-right font-mono">
                  {Math.round(r.away_win_prob * 100)}%
                </td>
                <td className="px-3 py-2">
                  <span
                    className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${
                      r.correct === 1
                        ? "border-win/30 bg-win/10 text-win"
                        : "border-loss/30 bg-loss/10 text-loss"
                    }`}
                  >
                    {r.correct === 1 ? "Correct" : "Wrong"}
                  </span>
                </td>
                <td className="px-3 py-2 text-slate-300">{r.confidence}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function InfoDensity({ rows }: { rows: PredictionRow[] }) {
  const cols: { key: keyof PredictionRow; label: string }[] = [
    { key: "info_density_context_tokens", label: "Context Tokens (total input size)" },
    { key: "info_density_vector_hits", label: "Vector Store Hits" },
    { key: "info_density_news_articles", label: "News Articles" },
    { key: "info_density_youtube_comments", label: "YouTube Comments" },
  ];
  const available = useMemo(
    () => cols.filter((c) => rows.some((r) => typeof r[c.key] === "number")),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [rows],
  );

  const [pick, setPick] = useState<keyof PredictionRow | null>(null);
  useEffect(() => {
    if (available.length > 0 && (pick === null || !available.some((c) => c.key === pick))) {
      setPick(available[0].key);
    }
  }, [available, pick]);

  if (available.length === 0 || !rows.some((r) => typeof r.brier_score === "number")) {
    return null;
  }
  const activePick = (pick ?? available[0].key) as keyof PredictionRow;
  const activeLabel = available.find((c) => c.key === activePick)?.label ?? String(activePick);

  const data = useMemo(
    () =>
      rows
        .filter(
          (r) =>
            typeof r[activePick] === "number" &&
            typeof r.brier_score === "number" &&
            !Number.isNaN(r.brier_score),
        )
        .map((r) => ({
          x: Number(r[activePick]),
          y: Number(r.brier_score),
          method: r.method,
        })),
    [rows, activePick],
  );

  // Continuous axis bounds with a tiny padding so points don't touch edges.
  const xMin = data.length ? Math.min(...data.map((d) => d.x)) : 0;
  const xMax = data.length ? Math.max(...data.map((d) => d.x)) : 1;
  const xPad = (xMax - xMin) * 0.04 || 1;
  const yMin = data.length ? Math.min(...data.map((d) => d.y)) : 0;
  const yMax = data.length ? Math.max(...data.map((d) => d.y)) : 1;
  const yPad = (yMax - yMin) * 0.08 || 0.05;

  // Pearson correlation — same as the Streamlit version's annotation.
  const pearson = useMemo(() => {
    const n = data.length;
    if (n < 3) return null;
    const mx = data.reduce((s, d) => s + d.x, 0) / n;
    const my = data.reduce((s, d) => s + d.y, 0) / n;
    let num = 0;
    let dx2 = 0;
    let dy2 = 0;
    for (const d of data) {
      const ex = d.x - mx;
      const ey = d.y - my;
      num += ex * ey;
      dx2 += ex * ex;
      dy2 += ey * ey;
    }
    const denom = Math.sqrt(dx2 * dy2);
    if (denom === 0) return null;
    return num / denom;
  }, [data]);

  // High vs low-info quartile bands (mirrors Streamlit's q25/q75 split).
  const sortedX = [...data].map((d) => d.x).sort((a, b) => a - b);
  const q = (p: number) => {
    if (sortedX.length === 0) return null;
    const idx = Math.max(0, Math.min(sortedX.length - 1, Math.floor((sortedX.length - 1) * p)));
    return sortedX[idx];
  };
  const q25 = q(0.25);
  const q75 = q(0.75);
  const loBrier =
    q25 != null
      ? data.filter((d) => d.x <= q25).reduce((s, d, _i, arr) => s + d.y / arr.length, 0)
      : null;
  const hiBrier =
    q75 != null
      ? data.filter((d) => d.x >= q75).reduce((s, d, _i, arr) => s + d.y / arr.length, 0)
      : null;
  const delta = loBrier != null && hiBrier != null ? hiBrier - loBrier : null;

  // Compact axis tick formatter — token counts can hit 80k+.
  const fmtAxis = (v: number) =>
    Math.abs(v) >= 1000 ? `${(v / 1000).toFixed(v >= 10000 ? 0 : 1)}k` : `${v.toFixed(0)}`;

  return (
    <Panel
      title="Information Density vs Prediction Quality (RQ1)"
      subtitle="Each point is one game-method prediction. Lower Brier = better. Negative correlation → more info improves predictions."
      action={
        <select
          className="input max-w-[18rem]"
          value={activePick as string}
          onChange={(e) => setPick(e.target.value as keyof PredictionRow)}
        >
          {available.map((c) => (
            <option key={c.key as string} value={c.key as string}>
              {c.label}
            </option>
          ))}
        </select>
      }
    >
      <ResponsiveContainer width="100%" height={360}>
        <ScatterChart margin={{ top: 16, right: 24, bottom: 28, left: 12 }}>
          <CartesianGrid stroke="rgba(255,255,255,0.06)" />
          <XAxis
            type="number"
            dataKey="x"
            domain={[xMin - xPad, xMax + xPad]}
            stroke="rgba(255,255,255,0.5)"
            tickFormatter={fmtAxis}
            label={{
              value: activeLabel,
              position: "insideBottom",
              offset: -12,
              fill: "rgba(255,255,255,0.55)",
              fontSize: 12,
            }}
          />
          <YAxis
            type="number"
            dataKey="y"
            domain={[Math.max(0, yMin - yPad), yMax + yPad]}
            stroke="rgba(255,255,255,0.5)"
            tickFormatter={(v) => v.toFixed(2)}
            label={{
              value: "Brier (lower is better)",
              angle: -90,
              position: "insideLeft",
              offset: 8,
              fill: "rgba(255,255,255,0.55)",
              fontSize: 12,
            }}
          />
          <ZAxis range={[64, 64]} />
          <Tooltip
            cursor={{ stroke: "rgba(255,255,255,0.18)", strokeDasharray: "3 3" }}
            content={
              <ChartTooltip
                sublabel={(payload: any[]) => {
                  const m = payload?.[0]?.payload?.method;
                  return m ? methodDisplayName(m) : null;
                }}
                valueFormatter={(value: any, name?: string) => {
                  if (typeof value !== "number") return [String(value), name ?? ""];
                  if (name === "x") return [fmtAxis(value), activeLabel];
                  if (name === "y") return [value.toFixed(4), "Brier"];
                  return [String(value), name ?? ""];
                }}
              />
            }
          />
          <Legend wrapperStyle={{ paddingTop: 12 }} />
          {Object.keys(COLORS).map((m) => (
            <Scatter
              key={m}
              name={methodDisplayName(m)}
              data={data.filter((d) => d.method === m)}
              fill={COLORS[m]}
              fillOpacity={0.75}
              stroke={COLORS[m]}
              strokeWidth={1.2}
            />
          ))}
        </ScatterChart>
      </ResponsiveContainer>

      <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatChip
          label="Pearson r"
          value={pearson == null ? "—" : pearson.toFixed(3)}
          hint={pearson == null ? "Need ≥ 3 points" : pearson < 0 ? "More info → better" : "More info → worse"}
          tone={pearson == null ? "default" : pearson < 0 ? "win" : "loss"}
        />
        <StatChip
          label="Low-info Brier"
          value={loBrier == null ? "—" : loBrier.toFixed(4)}
          hint="≤25th percentile"
        />
        <StatChip
          label="High-info Brier"
          value={hiBrier == null ? "—" : hiBrier.toFixed(4)}
          hint="≥75th percentile"
        />
        <StatChip
          label="Δ (high − low)"
          value={delta == null ? "—" : `${delta >= 0 ? "+" : ""}${delta.toFixed(4)}`}
          hint={delta == null ? "—" : delta > 0 ? "High-info games harder" : "High-info games easier"}
          tone={delta == null ? "default" : delta > 0 ? "loss" : "win"}
        />
      </div>
    </Panel>
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

function prettyMetric(m: string) {
  return m.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function fmt(v: number | undefined, m: string) {
  if (typeof v !== "number" || Number.isNaN(v)) return "—";
  if (["accuracy", "precision", "recall", "f1"].includes(m)) {
    return `${(v * 100).toFixed(1)}%`;
  }
  return formatNumber(v, 4);
}



function BacktestLogPane({
  status,
  output,
  startedAt,
  finishedAt,
  exitCode,
}: {
  status: "idle" | "running" | "done" | "error" | "timeout";
  output: string[];
  startedAt: number | null;
  finishedAt: number | null;
  exitCode: number | null;
}) {
  const [expanded, setExpanded] = useState(true);
  const ref = useRef<HTMLDivElement>(null);

  // Auto-scroll while live.
  useEffect(() => {
    if (status === "running" && ref.current) {
      ref.current.scrollTop = ref.current.scrollHeight;
    }
  }, [output.length, status]);

  const duration =
    startedAt != null
      ? Math.max(0, Math.round(((finishedAt ?? Date.now() / 1000) - startedAt)))
      : null;

  const Icon = status === "running" ? Loader2 : status === "done" ? CheckCircle2 : XCircle;
  const tone =
    status === "running"
      ? "border-accent/30 bg-accent/5 text-accent"
      : status === "done"
      ? "border-win/30 bg-win/5 text-win"
      : "border-loss/30 bg-loss/5 text-loss";

  return (
    <div className={cn("rounded-2xl border p-5 shadow-card", tone)}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Terminal className="h-4 w-4" />
          <span className="font-display text-sm font-semibold">
            Backtest log
          </span>
          <span
            className={cn(
              "rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider",
              status === "running"
                ? "border-accent/40 bg-accent/15 text-accent"
                : status === "done"
                ? "border-win/30 bg-win/10 text-win"
                : status === "idle"
                ? "border-white/10 bg-white/[0.04] text-slate-400"
                : "border-loss/30 bg-loss/10 text-loss",
            )}
          >
            <Icon
              className={cn(
                "mr-1 inline h-3 w-3",
                status === "running" && "animate-spin",
              )}
            />
            {status === "running"
              ? "Running"
              : status === "done"
              ? "Done"
              : status === "error"
              ? "Error"
              : status === "timeout"
              ? "Timed out"
              : "Idle"}
          </span>
          {duration != null && (
            <span className="text-xs text-slate-500">{duration}s</span>
          )}
          {exitCode != null && exitCode !== 0 && (
            <span className="text-xs text-loss">exit {exitCode}</span>
          )}
        </div>

        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200"
        >
          <ChevronDown
            className={cn(
              "h-3.5 w-3.5 transition-transform",
              expanded ? "rotate-0" : "-rotate-90",
            )}
          />
          {expanded ? "Hide" : "Show"} ({output.length} lines)
        </button>
      </div>

      <p className="mt-1 text-xs text-slate-500">
        Output streams from <span className="font-mono text-slate-400">nba_backtest.py</span>{" "}
        in real time. Identical lines are mirrored to the FastAPI server's terminal.
        Per-game caching under <span className="font-mono text-slate-400">data/backtest_cache/</span>{" "}
        keeps repeats cheap.
      </p>

      {expanded && (
        <div
          ref={ref}
          className="scroll-thin mt-3 max-h-96 overflow-y-auto rounded-xl border border-white/[0.06] bg-bg/60 p-4 font-mono text-[11px] leading-relaxed"
        >
          {output.length === 0 ? (
            <span className="text-slate-500">Waiting for output…</span>
          ) : (
            output.map((line, i) => (
              <div
                key={i}
                className={cn(
                  "whitespace-pre-wrap break-words",
                  line.startsWith("[runner")
                    ? "text-loss"
                    : line.startsWith("$ ")
                    ? "text-accent"
                    : line.includes("ERROR") || line.includes("Error")
                    ? "text-loss"
                    : line.startsWith("===")
                    ? "text-court-glow"
                    : "text-slate-300",
                )}
              >
                {line}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
