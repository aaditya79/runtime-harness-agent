import { Injury } from "@/types";
import { Panel } from "./Panel";
import { Activity } from "lucide-react";

interface Props {
  homeTeam: string;
  awayTeam: string;
  homeInjuries: Injury[];
  awayInjuries: Injury[];
}

export function InjurySummary({ homeTeam, awayTeam, homeInjuries, awayInjuries }: Props) {
  return (
    <Panel title="Injury & Availability" subtitle="Latest reports">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Column team={awayTeam} list={awayInjuries} />
        <Column team={homeTeam} list={homeInjuries} />
      </div>
    </Panel>
  );
}

function Column({ team, list }: { team: string; list: Injury[] }) {
  return (
    <div className="space-y-3 rounded-xl border border-white/[0.06] bg-bg-panel2/40 p-4">
      <div className="flex items-center justify-between">
        <h4 className="font-display text-sm font-semibold text-slate-100">{team}</h4>
        <span className="label">{list.length} reported</span>
      </div>
      {list.length === 0 ? (
        <div className="flex items-center gap-2 rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2 text-xs text-slate-500">
          <Activity className="h-3.5 w-3.5" />
          No reported injuries.
        </div>
      ) : (
        <ul className="space-y-2">
          {list.slice(0, 8).map((inj, i) => (
            <li
              key={`${inj.player}-${i}`}
              className="flex items-start justify-between gap-3 rounded-lg border border-white/[0.05] bg-white/[0.02] px-3 py-2"
            >
              <div className="min-w-0">
                <div className="flex flex-wrap items-baseline gap-2">
                  <span className="font-medium text-slate-100">{inj.player}</span>
                  {inj.position && (
                    <span className="text-[11px] uppercase tracking-wider text-slate-500">
                      {inj.position}
                    </span>
                  )}
                </div>
                {inj.comment && (
                  <p className="mt-1 line-clamp-2 text-xs text-slate-400">{inj.comment}</p>
                )}
              </div>
              <StatusBadge status={inj.status} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const lower = status.toLowerCase();
  let cls = "border-white/10 bg-white/[0.04] text-slate-300";
  if (lower === "out") cls = "border-loss/30 bg-loss/10 text-loss";
  else if (lower.includes("doubt")) cls = "border-warn/30 bg-warn/10 text-warn";
  else if (lower.includes("questionable") || lower.includes("day")) cls = "border-court/30 bg-court/10 text-court-glow";
  return (
    <span
      className={`shrink-0 rounded-full border px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider ${cls}`}
    >
      {status || "—"}
    </span>
  );
}
