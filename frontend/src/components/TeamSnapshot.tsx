import { TeamStats } from "@/types";
import { Panel } from "./Panel";
import { StatChip } from "./StatChip";
import { formatSigned } from "@/lib/utils";

interface Props {
  homeTeam: string;
  awayTeam: string;
  homeStats?: TeamStats;
  awayStats?: TeamStats;
}

export function TeamSnapshot({ homeTeam, awayTeam, homeStats, awayStats }: Props) {
  return (
    <Panel title="Team Snapshot" subtitle="Last 10 games · current season">
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <Column heading={awayTeam} stats={awayStats} side="away" />
        <Column heading={homeTeam} stats={homeStats} side="home" />
      </div>
    </Panel>
  );
}

function Column({
  heading,
  stats,
  side,
}: {
  heading: string;
  stats?: TeamStats;
  side: "home" | "away";
}) {
  const fg = stats?.avg_fg_pct_last_10;
  return (
    <div className="space-y-3">
      <div className="flex items-baseline justify-between">
        <h4 className="font-display text-base font-semibold text-slate-100">{heading}</h4>
        <span className={side === "home" ? "label text-accent" : "label"}>
          {side === "home" ? "Home" : "Away"}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-2.5 lg:grid-cols-3">
        <StatChip label="Season Record" value={stats?.season_record ?? "—"} />
        <StatChip label="Last 10" value={stats?.last_10_record ?? "—"} />
        <StatChip
          label="Avg PPG"
          value={
            typeof stats?.avg_points_last_10 === "number"
              ? stats.avg_points_last_10.toFixed(1)
              : "—"
          }
        />
        <StatChip
          label="Avg +/-"
          value={formatSigned(stats?.avg_plus_minus_last_10, 1)}
          tone={
            typeof stats?.avg_plus_minus_last_10 === "number"
              ? stats.avg_plus_minus_last_10 > 0
                ? "win"
                : "loss"
              : "default"
          }
        />
        <StatChip
          label="FG%"
          value={typeof fg === "number" ? `${(fg * 100).toFixed(1)}%` : "—"}
        />
        <StatChip
          label="Last Game"
          value={
            stats?.last_game ? (
              <span>
                {stats.last_game.result}{" "}
                <span className="text-xs font-medium text-slate-500">
                  · {stats.last_game.points}
                </span>
              </span>
            ) : (
              "—"
            )
          }
          tone={stats?.last_game?.result === "W" ? "win" : stats?.last_game ? "loss" : "default"}
          hint={stats?.last_game?.matchup}
        />
      </div>
    </div>
  );
}
