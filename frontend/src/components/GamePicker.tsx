import { Calendar, ChevronRight } from "lucide-react";
import { UpcomingGame } from "@/types";
import { cn } from "@/lib/utils";

interface Props {
  games: UpcomingGame[];
  value?: string;
  onChange: (gameId: string) => void;
  loading?: boolean;
}

export function GamePicker({ games, value, onChange, loading }: Props) {
  if (loading) {
    return (
      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div
            key={i}
            className="h-20 animate-pulse rounded-xl border border-white/[0.05] bg-white/[0.04]"
          />
        ))}
      </div>
    );
  }

  if (games.length === 0) {
    return (
      <div className="rounded-xl border border-warn/30 bg-warn/5 p-4 text-sm text-warn">
        No upcoming games found in the live odds feed. Re-run the odds pipeline to refresh today's
        slate.
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
      {games.map((g) => {
        const active = g.game_id === value;
        return (
          <button
            key={g.game_id}
            type="button"
            onClick={() => onChange(g.game_id)}
            className={cn(
              "group flex items-center justify-between gap-3 rounded-xl border p-3 text-left transition-all",
              active
                ? "border-accent/40 bg-accent/10 shadow-ember"
                : "border-white/[0.06] bg-white/[0.02] hover:border-white/20 hover:bg-white/[0.04]",
            )}
          >
            <div className="min-w-0">
              <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.18em] text-slate-500">
                <Calendar className="h-3 w-3" />
                {g.commence_time_label}
              </div>
              <div className="mt-1 truncate font-display text-sm font-semibold text-slate-100">
                <span className="text-slate-300">{g.away_team}</span>
                <span className="mx-1.5 text-slate-500">@</span>
                <span>{g.home_team}</span>
              </div>
            </div>
            <ChevronRight
              className={cn(
                "h-4 w-4 shrink-0 transition-all",
                active ? "text-accent" : "text-slate-500 group-hover:translate-x-0.5",
              )}
            />
          </button>
        );
      })}
    </div>
  );
}
