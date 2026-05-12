import { SimilarGame } from "@/types";
import { Panel } from "./Panel";

export function SimilarGames({ games }: { games: SimilarGame[] }) {
  if (!games || games.length === 0) return null;
  return (
    <Panel
      title="Similar Past Matchups"
      subtitle="Top retrievals from the ChromaDB vector store · used by the agent to ground predictions in real precedent"
    >
      <div className="space-y-2">
        {games.map((g, i) => {
          const desc = g.game_description || "Unknown game";
          const meta = g.metadata ?? {};
          const outcome = (meta.outcome ?? "").toString().toLowerCase();
          const outcomeIsWin = outcome === "w" || outcome === "win" || outcome === "1";
          const outcomeIsLoss = outcome === "l" || outcome === "loss" || outcome === "0";
          const sim = g.similarity_score ?? g.distance;
          return (
            <div
              key={i}
              className="flex items-start gap-3 rounded-xl border border-white/[0.05] bg-white/[0.02] px-4 py-3"
            >
              <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-white/10 font-mono text-xs text-slate-400">
                {i + 1}
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-sm text-slate-100">{desc}</div>
                <div className="mt-0.5 flex flex-wrap gap-2 text-[11px] text-slate-500">
                  {meta.game_date && <span>{String(meta.game_date)}</span>}
                  {meta.team && <span>· {String(meta.team)}</span>}
                  {meta.season && <span>· {String(meta.season)}</span>}
                </div>
              </div>
              <div className="flex flex-col items-end gap-1 text-right">
                {outcomeIsWin && (
                  <span className="rounded-full border border-win/30 bg-win/10 px-2 py-0.5 text-[10px] font-bold uppercase text-win">
                    Win
                  </span>
                )}
                {outcomeIsLoss && (
                  <span className="rounded-full border border-loss/30 bg-loss/10 px-2 py-0.5 text-[10px] font-bold uppercase text-loss">
                    Loss
                  </span>
                )}
                {typeof sim === "number" && (
                  <span className="font-mono text-[10px] text-slate-500">
                    sim {sim.toFixed(3)}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}
