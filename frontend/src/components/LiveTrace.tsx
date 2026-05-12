import { useEffect, useRef } from "react";
import { Activity } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  status: string;
  lines: string[];
  active: boolean;
}

export function LiveTrace({ status, lines, active }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [lines.length]);

  return (
    <div className="panel relative overflow-hidden p-5">
      <div className="pointer-events-none absolute -right-8 -top-8 h-28 w-28 rounded-full bg-accent/20 blur-3xl" />
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Activity className={cn("h-4 w-4", active ? "animate-pulse-dot text-accent" : "text-slate-400")} />
          <span className="font-display text-sm font-semibold text-slate-100">
            Live Analysis Progress
          </span>
        </div>
        <span
          className={cn(
            "rounded-full border px-3 py-1 text-xs font-bold uppercase tracking-wider",
            active
              ? "border-accent/30 bg-accent/10 text-accent"
              : "border-white/10 bg-white/[0.04] text-slate-400",
          )}
        >
          {status}
        </span>
      </div>

      <p className="mt-2 text-xs text-slate-500">
        Watch the model gather evidence, call tools, and synthesise its position in real time.
      </p>

      <div
        ref={scrollRef}
        className="scroll-thin mt-3 max-h-72 overflow-y-auto rounded-xl border border-white/[0.06] bg-bg/60 p-4 font-mono text-[12px] leading-relaxed"
      >
        {lines.length === 0 ? (
          <span className="text-slate-500">Starting analysis...</span>
        ) : (
          lines.map((line, i) => <Line key={i} text={line} />)
        )}
      </div>
    </div>
  );
}

function Line({ text }: { text: string }) {
  let cls = "text-slate-300";
  if (text.includes("FINAL REPORT") || text.includes("FINAL SYNTHESIZED REPORT")) {
    cls = "text-accent-glow font-semibold";
  } else if (text.includes("DEBATE ROUND")) {
    cls = "text-court-glow font-semibold";
  } else if (text.includes("PHASE")) {
    cls = "text-accent font-semibold";
  } else if (text.startsWith("Step ") || text.startsWith("  Step ")) {
    cls = "text-win";
  } else if (text.startsWith("ACTION") || text.includes("ACTION")) {
    cls = "text-court-glow";
  } else if (text.startsWith("OBSERVATION")) {
    cls = "text-slate-400";
  } else if (text.startsWith("==") || text.startsWith("##")) {
    cls = "text-slate-500";
  }
  return <div className={cn("whitespace-pre-wrap break-words", cls)}>{text}</div>;
}
