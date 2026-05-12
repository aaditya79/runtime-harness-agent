import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  CloudDownload,
  Database,
  Download,
  Loader2,
  Play,
  RefreshCw,
} from "lucide-react";
import { api } from "@/lib/api";
import { downloadJson, methodDisplayName } from "@/lib/utils";
import { Panel } from "@/components/Panel";
import { GamePicker } from "@/components/GamePicker";
import { AnalysisModePicker, Mode } from "@/components/AnalysisModePicker";
import { MatchupHeader } from "@/components/MatchupHeader";
import { TeamSnapshot } from "@/components/TeamSnapshot";
import { InjurySummary } from "@/components/InjurySummary";
import { SentimentSummary } from "@/components/SentimentSummary";
import { LiveTrace } from "@/components/LiveTrace";
import { AnalysisReport } from "@/components/AnalysisReport";
import { CompareCards } from "@/components/CompareCards";
import { useStreamingAnalysis } from "@/hooks/useStreamingAnalysis";
import type {
  AnalysisMode,
  MarketConsensus,
  ParsedReport,
  SimilarGame,
  UpcomingGame,
} from "@/types";

export default function MatchupPage() {
  const qc = useQueryClient();
  const upcoming = useQuery({ queryKey: ["upcoming"], queryFn: api.upcoming });
  const games = upcoming.data ?? [];

  const [pipelineMessage, setPipelineMessage] = useState<{
    tone: "ok" | "warn" | "error";
    text: string;
  } | null>(null);

  const refreshOddsMut = useMutation({
    mutationFn: api.refreshOdds,
    onSuccess: (res) => {
      if (res.ok) {
        setPipelineMessage({ tone: "ok", text: "Live odds refresh started. Status updates on the Data page." });
        qc.invalidateQueries({ queryKey: ["upcoming"] });
        qc.invalidateQueries({ queryKey: ["pipelines-status"] });
      } else if (res.rate_limited) {
        setPipelineMessage({
          tone: "warn",
          text: `Cooldown active. Try again in ${res.cooldown_remaining ?? 60}s.`,
        });
      } else {
        setPipelineMessage({
          tone: "error",
          text: res.error ?? "Odds pipeline failed. See server logs for details.",
        });
      }
    },
    onError: (err: unknown) => {
      const message = err instanceof Error ? err.message : "Refresh failed";
      setPipelineMessage({ tone: "error", text: message });
    },
  });

  // Polled pipeline status — used to detect when the data pipelines haven't
  // been run yet so we can surface a setup banner.
  const pipelineStatuses = useQuery({
    queryKey: ["pipelines-status"],
    queryFn: api.pipelinesStatus,
    refetchInterval: 10_000,
  });
  const missingArtifacts = useMemo(() => {
    const data = pipelineStatuses.data;
    if (!data) return [];
    const required = ["data", "vector_store"] as const;
    const out: { name: string; missing: string[] }[] = [];
    for (const name of required) {
      const s = data[name];
      if (!s) continue;
      const missing = s.produces_present.filter((p) => !p.exists).map((p) => p.path);
      if (missing.length > 0) out.push({ name: s.title, missing });
    }
    return out;
  }, [pipelineStatuses.data]);

  const [selectedId, setSelectedId] = useState<string | undefined>();
  useEffect(() => {
    if (!selectedId && games.length > 0) {
      setSelectedId(games[0].game_id);
    }
  }, [selectedId, games]);

  const game = useMemo(
    () => games.find((g) => g.game_id === selectedId) ?? games[0],
    [selectedId, games],
  );

  const homeTeam = game?.home_team ?? "";
  const awayTeam = game?.away_team ?? "";
  const homeAbbr = game?.home_abbr ?? "";
  const awayAbbr = game?.away_abbr ?? "";

  const matchup = useQuery({
    queryKey: ["matchup", homeTeam, awayTeam],
    queryFn: () => api.matchup(homeTeam, awayTeam),
    enabled: Boolean(homeTeam && awayTeam),
  });

  const consensus = useQuery({
    queryKey: ["consensus", homeTeam, awayTeam],
    queryFn: () => api.marketConsensus(homeTeam, awayTeam),
    enabled: Boolean(homeTeam && awayTeam),
  });

  const similar = useQuery({
    queryKey: ["similar", homeAbbr, awayAbbr],
    queryFn: () => api.similar(homeAbbr, awayAbbr),
    enabled: Boolean(homeAbbr && awayAbbr),
  });

  const [mode, setMode] = useState<Mode>("multi_agent");
  const stream = useStreamingAnalysis();

  // Compare All state
  const [compareLoading, setCompareLoading] = useState<null | "multi_agent" | "single_agent" | "cot" | "done">(null);
  const [compareReports, setCompareReports] = useState<{
    multi?: { report: ParsedReport | null; raw: any; trace: string };
    single?: { report: ParsedReport | null; raw: any; trace: string };
    cot?: { report: ParsedReport | null; raw: any; trace: string };
  }>({});

  const runDisabled =
    !game ||
    !homeAbbr ||
    !awayAbbr ||
    stream.loading ||
    compareLoading !== null && compareLoading !== "done";

  async function runOne() {
    if (!game) return;
    if (mode === "compare") return runCompare();
    setCompareReports({});
    setCompareLoading(null);
    stream.reset();
    await stream.start({
      mode: mode as AnalysisMode,
      home_team: homeTeam,
      away_team: awayTeam,
      home_abbr: homeAbbr,
      away_abbr: awayAbbr,
      game_date: game.commence_time.slice(0, 10),
    });
  }

  async function runCompare() {
    if (!game) return;
    stream.reset();
    setCompareReports({});
    const baseReq = {
      home_team: homeTeam,
      away_team: awayTeam,
      home_abbr: homeAbbr,
      away_abbr: awayAbbr,
      game_date: game.commence_time.slice(0, 10),
    };
    try {
      setCompareLoading("multi_agent");
      const multi = await api.analysisRun({ ...baseReq, mode: "multi_agent" });
      setCompareReports((p) => ({ ...p, multi }));

      setCompareLoading("single_agent");
      const single = await api.analysisRun({ ...baseReq, mode: "single_agent" });
      setCompareReports((p) => ({ ...p, single }));

      setCompareLoading("cot");
      const cot = await api.analysisRun({ ...baseReq, mode: "cot" });
      setCompareReports((p) => ({ ...p, cot }));

      setCompareLoading("done");
    } catch (err) {
      console.error(err);
      setCompareLoading(null);
    }
  }

  const handleDownload = () => {
    if (!game) return;
    if (mode === "compare") {
      downloadJson(
        `matchodds_compare_${awayAbbr}_at_${homeAbbr}_${game.commence_time.slice(0, 10)}.json`,
        {
          mode: "Compare All",
          game: `${awayTeam} vs ${homeTeam}, ${game.commence_time.slice(0, 10)}`,
          generated_at: new Date().toISOString(),
          multi_agent: compareReports.multi,
          single_agent: compareReports.single,
          cot: compareReports.cot,
        },
      );
      return;
    }
    if (!stream.result) return;
    downloadJson(
      `matchodds_report_${awayAbbr}_at_${homeAbbr}_${game.commence_time.slice(0, 10)}.json`,
      {
        product: "MatchOdds AI",
        mode: methodDisplayName(stream.result.mode),
        game: `${awayTeam} vs ${homeTeam}, ${game.commence_time.slice(0, 10)}`,
        generated_at: stream.result.generatedAt,
        summary_report: stream.result.report,
        full_result: stream.result.raw,
      },
    );
  };

  const showLiveTrace = stream.loading || (stream.result && stream.lines.length > 0);
  const compareItems = [
    { mode: "multi_agent", report: compareReports.multi?.report ?? null },
    { mode: "single_agent", report: compareReports.single?.report ?? null },
    { mode: "cot", report: compareReports.cot?.report ?? null },
  ];

  return (
    <div className="space-y-6">
      <Hero />

      {missingArtifacts.length > 0 && (
        <div className="flex flex-col gap-3 rounded-2xl border border-warn/30 bg-warn/[0.06] p-5 text-sm text-warn md:flex-row md:items-center md:justify-between">
          <div className="flex items-start gap-3">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <div>
              <strong>First-time setup needed.</strong> The agent tools read CSVs and a
              ChromaDB collection that haven't been built yet:
              <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-warn/80">
                {missingArtifacts.map((m) => (
                  <li key={m.name}>
                    <span className="font-mono">{m.missing.join(", ")}</span>{" "}
                    <span className="text-warn/60">({m.name})</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
          <Link to="/data" className="btn-primary shrink-0">
            <Database className="h-4 w-4" />
            Open Data page
            <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      )}

      <Panel
        title="Select Game"
        subtitle={
          games.length > 0
            ? `Latest game in odds feed: ${games[games.length - 1].commence_time_label}`
            : "Pick an upcoming matchup to analyse"
        }
        action={
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => {
                setPipelineMessage(null);
                refreshOddsMut.mutate();
              }}
              disabled={refreshOddsMut.isPending}
              className="btn-ghost px-3 py-2 text-xs"
              title="Re-run nba_odds_pipeline.py to refresh today's slate (60s cooldown)"
            >
              {refreshOddsMut.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <CloudDownload className="h-3.5 w-3.5" />
              )}
              Refresh odds
            </button>
            <button
              type="button"
              onClick={() => upcoming.refetch()}
              className="btn-ghost px-3 py-2 text-xs"
              title="Re-read odds_live.csv from disk"
            >
              <RefreshCw className="h-3.5 w-3.5" /> Reload list
            </button>
          </div>
        }
      >
        {pipelineMessage && (
          <div
            className={`mb-3 rounded-xl border px-3 py-2 text-xs ${
              pipelineMessage.tone === "ok"
                ? "border-win/30 bg-win/5 text-win"
                : pipelineMessage.tone === "warn"
                ? "border-warn/30 bg-warn/5 text-warn"
                : "border-loss/30 bg-loss/5 text-loss"
            }`}
          >
            {pipelineMessage.text}
          </div>
        )}
        <GamePicker
          games={games as UpcomingGame[]}
          value={selectedId}
          onChange={setSelectedId}
          loading={upcoming.isLoading || refreshOddsMut.isPending}
        />
      </Panel>

      {game && (
        <>
          <MatchupHeader
            homeTeam={homeTeam}
            awayTeam={awayTeam}
            homeAbbr={homeAbbr}
            awayAbbr={awayAbbr}
            homeLogo={matchup.data?.home_logo}
            awayLogo={matchup.data?.away_logo}
            date={new Date(game.commence_time).toLocaleString(undefined, {
              dateStyle: "full",
              timeStyle: "short",
            })}
          />

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <TeamSnapshot
              homeTeam={homeTeam}
              awayTeam={awayTeam}
              homeStats={matchup.data?.home_stats}
              awayStats={matchup.data?.away_stats}
            />
            <InjurySummary
              homeTeam={homeTeam}
              awayTeam={awayTeam}
              homeInjuries={matchup.data?.home_injuries ?? []}
              awayInjuries={matchup.data?.away_injuries ?? []}
            />
          </div>

          <SentimentSummary
            homeTeam={homeTeam}
            awayTeam={awayTeam}
            home={matchup.data?.home_sentiment}
            away={matchup.data?.away_sentiment}
          />
        </>
      )}

      <Panel
        title="Analysis Mode"
        subtitle="Pick a reasoning system. Each one trades depth, transparency, and speed differently."
      >
        <AnalysisModePicker value={mode} onChange={setMode} />

        <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-white/[0.06] pt-5">
          <div className="text-xs text-slate-500">
            {mode === "compare"
              ? "Runs multi-agent debate, single-agent, and chain-of-thought sequentially."
              : "Streams the live trace as the model gathers evidence."}
          </div>
          <div className="flex items-center gap-2">
            {(stream.result || compareLoading === "done") && (
              <button type="button" onClick={handleDownload} className="btn">
                <Download className="h-4 w-4" />
                Download {mode === "compare" ? "Comparison" : "Report"}
              </button>
            )}
            <button
              type="button"
              onClick={runOne}
              disabled={runDisabled}
              className="btn-primary"
            >
              {stream.loading || (compareLoading && compareLoading !== "done") ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Play className="h-4 w-4" />
              )}
              Run Analysis
            </button>
          </div>
        </div>
      </Panel>

      {stream.error && (
        <div className="flex items-start gap-3 rounded-xl border border-loss/30 bg-loss/5 p-4 text-sm text-loss">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{stream.error}</span>
        </div>
      )}

      {showLiveTrace && mode !== "compare" && (
        <LiveTrace
          status={stream.status}
          lines={stream.lines}
          active={stream.loading}
        />
      )}

      {compareLoading && compareLoading !== "done" && mode === "compare" && (
        <Panel title="Running Comparison">
          <div className="space-y-3">
            <CompareStep label="Multi-Agent Debate" current={compareLoading} idx="multi_agent" />
            <CompareStep label="Single Agent" current={compareLoading} idx="single_agent" />
            <CompareStep label="Chain-of-Thought" current={compareLoading} idx="cot" />
          </div>
        </Panel>
      )}

      {/* Single-mode result */}
      {mode !== "compare" && stream.result?.report && (
        <AnalysisReport
          report={stream.result.report}
          raw={stream.result.raw}
          mode={stream.result.mode}
          homeTeam={homeTeam}
          awayTeam={awayTeam}
          consensus={consensus.data as MarketConsensus | undefined}
          similar={similar.data as SimilarGame[] | undefined}
        />
      )}

      {/* Compare-mode results */}
      {mode === "compare" && compareLoading === "done" && (
        <>
          <CompareCards items={compareItems} />
          {compareReports.multi?.report && (
            <Section title="Multi-Agent Debate">
              <AnalysisReport
                report={compareReports.multi.report}
                raw={compareReports.multi.raw}
                mode="multi_agent"
                homeTeam={homeTeam}
                awayTeam={awayTeam}
                consensus={consensus.data as MarketConsensus | undefined}
                similar={similar.data as SimilarGame[] | undefined}
              />
            </Section>
          )}
          {compareReports.single?.report && (
            <Section title="Single Agent">
              <AnalysisReport
                report={compareReports.single.report}
                raw={compareReports.single.raw}
                mode="single_agent"
                homeTeam={homeTeam}
                awayTeam={awayTeam}
                consensus={consensus.data as MarketConsensus | undefined}
                similar={similar.data as SimilarGame[] | undefined}
              />
            </Section>
          )}
          {compareReports.cot?.report && (
            <Section title="Chain-of-Thought">
              <AnalysisReport
                report={compareReports.cot.report}
                raw={compareReports.cot.raw}
                mode="cot"
                homeTeam={homeTeam}
                awayTeam={awayTeam}
                consensus={consensus.data as MarketConsensus | undefined}
                similar={similar.data as SimilarGame[] | undefined}
              />
            </Section>
          )}
        </>
      )}

      {mode !== "compare" && stream.result && !stream.result.report && (
        <div className="rounded-xl border border-warn/30 bg-warn/5 p-4 text-sm text-warn">
          <strong>Could not parse the model's structured output.</strong> The raw trace is shown
          above. Try re-running, or pick a different analysis mode.
        </div>
      )}
    </div>
  );
}

function Hero() {
  return (
    <div className="relative overflow-hidden rounded-3xl border border-white/[0.06] bg-bg-panel/60 p-7">
      <div className="pointer-events-none absolute -right-24 -top-24 h-64 w-64 rounded-full bg-accent/20 blur-3xl" />
      <div className="pointer-events-none absolute -left-12 bottom-0 h-48 w-48 rounded-full bg-court/20 blur-3xl" />
      <div className="relative grid grid-cols-1 items-center gap-4 md:grid-cols-[1.4fr_1fr]">
        <div>
          <span className="chip-accent">Research-only · Not financial advice</span>
          <h1 className="mt-3 text-balance font-display text-4xl font-bold tracking-tight text-slate-50 md:text-5xl">
            NBA matchup intelligence,{" "}
            <span className="bg-gradient-to-r from-accent via-accent-glow to-court-glow bg-clip-text text-transparent">
              built for sharp eyes
            </span>
            .
          </h1>
          <p className="mt-3 max-w-xl text-sm leading-relaxed text-slate-400 md:text-base">
            Pre-game stats, injuries, market consensus, and historical precedent — fed through
            multi-agent debate, single-agent reasoning, or chain-of-thought baselines. Compare them
            side by side.
          </p>
        </div>
        <div className="grid grid-cols-3 gap-2.5">
          <HeroStat value="3" label="Reasoning systems" tone="accent" />
          <HeroStat value="6" label="Data sources" tone="court" />
          <HeroStat value="22.9k" label="Vector games" tone="win" />
        </div>
      </div>
    </div>
  );
}

function HeroStat({
  value,
  label,
  tone,
}: {
  value: string;
  label: string;
  tone: "accent" | "court" | "win";
}) {
  const colorMap = {
    accent: "text-accent-glow",
    court: "text-court-glow",
    win: "text-win",
  }[tone];
  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] p-3 text-center">
      <div className={`font-display text-2xl font-bold ${colorMap}`}>{value}</div>
      <div className="mt-0.5 text-[10px] uppercase tracking-[0.18em] text-slate-500">{label}</div>
    </div>
  );
}

function CompareStep({
  label,
  current,
  idx,
}: {
  label: string;
  current: string | null;
  idx: string;
}) {
  const order: Record<string, number> = {
    multi_agent: 0,
    single_agent: 1,
    cot: 2,
    done: 3,
  };
  const pos = order[idx] ?? 0;
  const cur = order[current ?? "multi_agent"] ?? 0;
  const state = cur > pos ? "done" : cur === pos ? "active" : "pending";
  return (
    <div
      className={`flex items-center justify-between rounded-lg border px-3 py-2 text-sm ${
        state === "done"
          ? "border-win/30 bg-win/5 text-win"
          : state === "active"
          ? "border-accent/30 bg-accent/5 text-accent"
          : "border-white/[0.05] bg-white/[0.02] text-slate-500"
      }`}
    >
      <span>{label}</span>
      {state === "done" && <span className="text-xs">✓ done</span>}
      {state === "active" && (
        <span className="flex items-center gap-1.5 text-xs">
          <Loader2 className="h-3 w-3 animate-spin" /> running
        </span>
      )}
      {state === "pending" && <span className="text-xs">queued</span>}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <span className="h-px flex-1 bg-gradient-to-r from-transparent via-accent/40 to-transparent" />
        <h3 className="font-display text-sm font-bold uppercase tracking-[0.22em] text-accent">
          {title}
        </h3>
        <span className="h-px flex-1 bg-gradient-to-r from-transparent via-accent/40 to-transparent" />
      </div>
      {children}
    </div>
  );
}
