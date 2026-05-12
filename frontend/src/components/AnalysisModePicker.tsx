import { Brain, Layers, Sparkles, Zap } from "lucide-react";
import { cn } from "@/lib/utils";

export type Mode = "single_agent" | "multi_agent" | "cot" | "compare";

const MODES: { id: Mode; title: string; copy: string; icon: any; tone: string }[] = [
  {
    id: "multi_agent",
    title: "Multi-Agent Debate",
    copy: "Three specialized agents debate, then a moderator synthesises. The deepest analysis.",
    icon: Layers,
    tone: "border-accent/30 bg-accent/5",
  },
  {
    id: "single_agent",
    title: "Single Agent",
    copy: "One ReAct agent gathers evidence iteratively and produces a direct recommendation.",
    icon: Brain,
    tone: "border-court/30 bg-court/5",
  },
  {
    id: "cot",
    title: "Chain-of-Thought",
    copy: "All evidence passed in one shot. Most transparent linear reasoning.",
    icon: Zap,
    tone: "border-win/30 bg-win/5",
  },
  {
    id: "compare",
    title: "Compare All",
    copy: "Run all three on the same matchup and put them side by side.",
    icon: Sparkles,
    tone: "border-warn/30 bg-warn/5",
  },
];

interface Props {
  value: Mode;
  onChange: (m: Mode) => void;
}

export function AnalysisModePicker({ value, onChange }: Props) {
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-4">
      {MODES.map((m) => {
        const active = m.id === value;
        const Icon = m.icon;
        return (
          <button
            key={m.id}
            type="button"
            onClick={() => onChange(m.id)}
            className={cn(
              "group relative flex flex-col items-start gap-2 rounded-2xl border p-4 text-left transition-all",
              active
                ? `${m.tone} ring-1 ring-accent/40 shadow-ember`
                : "border-white/[0.06] bg-white/[0.02] hover:border-white/15 hover:bg-white/[0.04]",
            )}
          >
            <div className={cn("flex h-9 w-9 items-center justify-center rounded-xl border", active ? "border-accent/40 bg-accent/15 text-accent-glow" : "border-white/10 bg-white/[0.04] text-slate-400")}>
              <Icon className="h-4 w-4" />
            </div>
            <div>
              <div className="font-display text-sm font-semibold text-slate-50">{m.title}</div>
              <p className="mt-1 text-xs leading-relaxed text-slate-400">{m.copy}</p>
            </div>
            {active && (
              <span className="absolute right-3 top-3 rounded-full border border-accent/40 bg-accent/15 px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest text-accent">
                Selected
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
