import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  Database,
  Loader2,
  Play,
  Stethoscope,
  Newspaper,
  Activity,
  Boxes,
  Clock,
} from "lucide-react";
import { api } from "@/lib/api";
import { Panel } from "@/components/Panel";
import { cn } from "@/lib/utils";
import type { PipelineName, PipelineStatus } from "@/types";

const ICON_MAP: Record<PipelineName, any> = {
  data: Database,
  injuries: Stethoscope,
  odds: Activity,
  news: Newspaper,
  vector_store: Boxes,
};

// Display order: data first (it's the dependency), then odds (fast), then
// the smaller refreshes, then the vector store last.
const ORDER: PipelineName[] = ["data", "odds", "injuries", "news", "vector_store"];

export default function PipelinesPage() {
  const qc = useQueryClient();

  const statuses = useQuery({
    queryKey: ["pipelines-status"],
    queryFn: api.pipelinesStatus,
    refetchInterval: (query) => {
      const data = query.state.data as Record<PipelineName, PipelineStatus> | undefined;
      if (!data) return 5_000;
      return Object.values(data).some((s) => s.status === "running") ? 1_500 : 5_000;
    },
  });

  const start = useMutation({
    mutationFn: api.pipelineStart,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pipelines-status"] }),
  });

  const data = statuses.data;
  const ordered = useMemo(() => {
    if (!data) return [] as PipelineStatus[];
    return ORDER.filter((n) => data[n]).map((n) => data[n]);
  }, [data]);

  const anyRunning = ordered.some((s) => s.status === "running");
  const allReady = ordered.every((s) =>
    s.produces_present.length === 0 ? true : s.produces_present.every((p) => p.exists),
  );

  return (
    <div className="space-y-6">
      <Hero allReady={allReady} anyRunning={anyRunning} />

      <Panel
        title="Data pipelines"
        subtitle="One-time setup. Run these in order on first launch; refresh later as needed."
      >
        {!data && <p className="body-muted">Loading status…</p>}
        {data && (
          <div className="space-y-3">
            {ordered.map((s) => (
              <PipelineCard
                key={s.name}
                status={s}
                disabled={start.isPending}
                onStart={() => start.mutate(s.name)}
              />
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}

function Hero({ allReady, anyRunning }: { allReady: boolean; anyRunning: boolean }) {
  return (
    <div className="relative overflow-hidden rounded-3xl border border-white/[0.06] bg-bg-panel/60 p-7">
      <div className="pointer-events-none absolute -right-12 -top-12 h-44 w-44 rounded-full bg-court/30 blur-3xl" />
      <span className="chip">Setup & data</span>
      <h1 className="mt-3 text-balance font-display text-3xl font-bold tracking-tight text-slate-50 md:text-4xl">
        Data pipelines
      </h1>
      <p className="mt-2 max-w-2xl text-sm text-slate-400">
        Each pipeline writes to <span className="font-mono text-xs text-slate-300">data/</span>{" "}
        and is read live by the agent tools. Run them once on first launch, then re-run
        whenever you want fresh data.
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-2 text-xs">
        {anyRunning ? (
          <span className="chip border-accent/30 bg-accent/10 text-accent">
            <Loader2 className="h-3 w-3 animate-spin" /> Pipeline running
          </span>
        ) : allReady ? (
          <span className="chip border-win/30 bg-win/10 text-win">
            <CheckCircle2 className="h-3 w-3" /> All required artifacts present
          </span>
        ) : (
          <span className="chip border-warn/30 bg-warn/10 text-warn">
            <AlertTriangle className="h-3 w-3" /> Some artifacts missing
          </span>
        )}
      </div>
    </div>
  );
}

function PipelineCard({
  status,
  disabled,
  onStart,
}: {
  status: PipelineStatus;
  disabled: boolean;
  onStart: () => void;
}) {
  const Icon = ICON_MAP[status.name];
  const [showOutput, setShowOutput] = useState(false);
  const cooldown = status.cooldown_remaining;
  const running = status.status === "running";
  const ready = status.produces_present.every((p) => p.exists);

  // Auto-open output while running so the user sees progress.
  useEffect(() => {
    if (running) setShowOutput(true);
  }, [running]);

  return (
    <div
      className={cn(
        "rounded-2xl border p-5 transition-all",
        running
          ? "border-accent/30 bg-accent/5 shadow-ember"
          : status.status === "error" || status.status === "timeout"
          ? "border-loss/30 bg-loss/5"
          : status.status === "done"
          ? "border-win/30 bg-win/5"
          : "border-white/[0.06] bg-bg-panel2/40",
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div
            className={cn(
              "flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border",
              running
                ? "border-accent/40 bg-accent/15 text-accent"
                : ready
                ? "border-win/30 bg-win/10 text-win"
                : "border-white/10 bg-white/[0.04] text-slate-300",
            )}
          >
            <Icon className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <h3 className="font-display text-base font-semibold text-slate-50">
              {status.title}
            </h3>
            <p className="mt-1 text-sm text-slate-400">{status.description}</p>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px]">
              <span className="chip">
                <Clock className="h-3 w-3" /> {status.eta}
              </span>
              <StatusPill status={status} />
              {status.last_run_at && (
                <span className="text-slate-500">
                  Last run: {timeAgo(status.last_run_at)}
                </span>
              )}
            </div>
          </div>
        </div>

        <button
          type="button"
          onClick={onStart}
          disabled={disabled || running || cooldown > 0}
          className="btn-primary"
          title={cooldown > 0 ? `Cooldown: ${cooldown}s` : `Run ${status.name}`}
        >
          {running ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Play className="h-4 w-4" />
          )}
          {running ? "Running" : cooldown > 0 ? `Wait ${cooldown}s` : "Run"}
        </button>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {status.produces_present.map((p) => (
          <div
            key={p.path}
            className={cn(
              "flex items-center justify-between rounded-lg border px-3 py-1.5 text-xs",
              p.exists
                ? "border-win/20 bg-win/5 text-win"
                : "border-loss/20 bg-loss/5 text-loss",
            )}
          >
            <span className="truncate font-mono">{p.path}</span>
            <span className="ml-2 text-[10px] uppercase tracking-wider">
              {p.exists ? "Present" : "Missing"}
            </span>
          </div>
        ))}
      </div>

      {(status.output_tail.length > 0 || running) && (
        <div className="mt-4">
          <button
            type="button"
            className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200"
            onClick={() => setShowOutput((v) => !v)}
          >
            <ChevronDown
              className={cn(
                "h-3.5 w-3.5 transition-transform",
                showOutput ? "rotate-0" : "-rotate-90",
              )}
            />
            {showOutput ? "Hide output" : "Show output"}
            <span className="text-slate-600">·</span>
            <span className="text-slate-600">{status.output_tail.length} lines</span>
          </button>
          {showOutput && <OutputPane lines={status.output_tail} live={running} />}
        </div>
      )}
    </div>
  );
}

function OutputPane({ lines, live }: { lines: string[]; live: boolean }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (live && ref.current) {
      ref.current.scrollTop = ref.current.scrollHeight;
    }
  }, [lines.length, live]);

  return (
    <div
      ref={ref}
      className="scroll-thin mt-2 max-h-72 overflow-y-auto rounded-xl border border-white/[0.06] bg-bg/60 p-3 font-mono text-[11px] leading-relaxed"
    >
      {lines.length === 0 ? (
        <span className="text-slate-500">Waiting for output…</span>
      ) : (
        lines.map((line, i) => (
          <div
            key={i}
            className={cn(
              "whitespace-pre-wrap break-words",
              line.startsWith("[") ? "text-loss" : "text-slate-300",
            )}
          >
            {line}
          </div>
        ))
      )}
    </div>
  );
}

function StatusPill({ status }: { status: PipelineStatus }) {
  const map = {
    idle: { cls: "border-white/10 bg-white/[0.04] text-slate-300", text: "Idle" },
    running: { cls: "border-accent/30 bg-accent/10 text-accent", text: "Running" },
    done: { cls: "border-win/30 bg-win/10 text-win", text: "Done" },
    error: { cls: "border-loss/30 bg-loss/10 text-loss", text: "Error" },
    timeout: { cls: "border-loss/30 bg-loss/10 text-loss", text: "Timed out" },
  } as const;
  const m = map[status.status] ?? map.idle;
  return (
    <span className={cn("rounded-full border px-2 py-0.5 font-bold uppercase tracking-wider", m.cls)}>
      {m.text}
    </span>
  );
}

function timeAgo(epoch: number): string {
  const diff = Math.max(0, Math.round(Date.now() / 1000 - epoch));
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.round(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)} hr ago`;
  return `${Math.round(diff / 86400)} d ago`;
}
