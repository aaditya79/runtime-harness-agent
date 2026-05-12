import { useCallback, useRef, useState } from "react";
import { AnalysisRunRequest, StreamEvent, streamAnalysis } from "@/lib/api";
import { ParsedReport } from "@/types";

interface CompletedAnalysis {
  report: ParsedReport | null;
  raw: any;
  trace: string;
  mode: string;
  generatedAt: string;
}

interface State {
  status: string;
  lines: string[];
  loading: boolean;
  error: string | null;
  result: CompletedAnalysis | null;
}

const initial: State = {
  status: "Idle",
  lines: [],
  loading: false,
  error: null,
  result: null,
};

export function useStreamingAnalysis() {
  const [state, setState] = useState<State>(initial);
  const abortRef = useRef<AbortController | null>(null);

  const start = useCallback(async (req: AnalysisRunRequest) => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setState({
      status: "Starting analysis…",
      lines: [],
      loading: true,
      error: null,
      result: null,
    });

    try {
      await streamAnalysis(
        req,
        (evt: StreamEvent) => {
          if (evt.event === "trace" && evt.line !== undefined) {
            setState((prev) => ({
              ...prev,
              status: evt.status ?? prev.status,
              lines: [...prev.lines, evt.line!],
            }));
          } else if (evt.event === "done") {
            setState((prev) => ({
              ...prev,
              status: "Analysis complete",
              loading: false,
              result: {
                report: evt.report ?? null,
                raw: evt.raw ?? {},
                trace: evt.trace ?? prev.lines.join("\n"),
                mode: evt.mode ?? req.mode,
                generatedAt: evt.generated_at ?? new Date().toISOString(),
              },
            }));
          } else if (evt.event === "error") {
            setState((prev) => ({
              ...prev,
              status: "Error",
              loading: false,
              error: evt.message ?? "Unknown error",
            }));
          }
        },
        ctrl.signal,
      );
    } catch (err: any) {
      if (ctrl.signal.aborted) return;
      setState((prev) => ({
        ...prev,
        status: "Error",
        loading: false,
        error: err?.message ?? "Stream failed",
      }));
    }
  }, []);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setState(initial);
  }, []);

  return { ...state, start, reset };
}
