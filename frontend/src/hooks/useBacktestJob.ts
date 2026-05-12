import { useCallback, useEffect, useRef, useState } from "react";
import { api, streamBacktest } from "@/lib/api";
import type { BacktestJobStatus } from "@/types";

interface State {
  status: BacktestJobStatus["status"];
  params: BacktestJobStatus["params"];
  startedAt: number | null;
  finishedAt: number | null;
  exitCode: number | null;
  output: string[];
  error: string | null;
}

const initial: State = {
  status: "idle",
  params: null,
  startedAt: null,
  finishedAt: null,
  exitCode: null,
  output: [],
  error: null,
};

/** Manages the lifecycle of a single backtest job: kickoff, live stream,
 * polling resync, and final completion notification.
 */
export function useBacktestJob(onComplete?: () => void) {
  const [state, setState] = useState<State>(initial);
  const abortRef = useRef<AbortController | null>(null);

  // Sync with the backend on mount in case a job is already running.
  useEffect(() => {
    let cancelled = false;
    api.backtestStatus().then((s) => {
      if (cancelled) return;
      setState({
        status: s.status,
        params: s.params,
        startedAt: s.started_at,
        finishedAt: s.finished_at,
        exitCode: s.exit_code,
        output: s.output_tail,
        error: null,
      });
      if (s.status === "running") {
        attachStream();
      }
    }).catch(() => {});
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const attachStream = useCallback(() => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    streamBacktest(
      (evt) => {
        if (evt.event === "snapshot") {
          try {
            const snap = JSON.parse(evt.data) as BacktestJobStatus;
            setState((prev) => ({
              ...prev,
              status: snap.status,
              params: snap.params,
              startedAt: snap.started_at,
              finishedAt: snap.finished_at,
              exitCode: snap.exit_code,
              output: snap.output_tail,
            }));
          } catch {
            // ignore
          }
        } else if (evt.event === "line") {
          setState((prev) => ({ ...prev, output: [...prev.output, evt.data] }));
        } else if (evt.event === "done") {
          try {
            const snap = JSON.parse(evt.data) as BacktestJobStatus;
            setState((prev) => ({
              ...prev,
              status: snap.status,
              finishedAt: snap.finished_at,
              exitCode: snap.exit_code,
            }));
          } catch {
            setState((prev) => ({ ...prev, status: "done" }));
          }
          onComplete?.();
        }
      },
      ctrl.signal,
    ).catch((err) => {
      if (ctrl.signal.aborted) return;
      setState((prev) => ({
        ...prev,
        error: err instanceof Error ? err.message : String(err),
      }));
    });
  }, [onComplete]);

  const start = useCallback(
    async (req: { n_games: number; season: string; min_history: number }) => {
      setState({ ...initial, status: "running", params: req });
      try {
        const res = await api.backtestRun(req);
        if (!res.ok) {
          // Already running — fall through to attach the live stream.
          setState((prev) => ({
            ...prev,
            params: res.status?.params ?? prev.params,
            output: res.status?.output_tail ?? prev.output,
            error: res.error ?? null,
          }));
        }
        attachStream();
      } catch (err) {
        setState((prev) => ({
          ...prev,
          status: "error",
          error: err instanceof Error ? err.message : String(err),
        }));
      }
    },
    [attachStream],
  );

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setState(initial);
  }, []);

  return { ...state, start, reset };
}
