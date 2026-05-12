import { TeamSentiment } from "@/types";
import { Panel } from "./Panel";
import { sentimentColor } from "@/lib/utils";

interface Props {
  homeTeam: string;
  awayTeam: string;
  home?: TeamSentiment;
  away?: TeamSentiment;
}

export function SentimentSummary({ homeTeam, awayTeam, home, away }: Props) {
  return (
    <Panel
      title="Media Sentiment"
      subtitle="Secondary signal · derived from recent NBA news coverage"
    >
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Card team={awayTeam} sent={away} />
        <Card team={homeTeam} sent={home} />
      </div>
    </Panel>
  );
}

function Card({ team, sent }: { team: string; sent?: TeamSentiment }) {
  const value = sent?.avg_sentiment;
  const tone = sentimentColor(value);
  const text = typeof value === "number" ? (value > 0 ? `+${value.toFixed(3)}` : value.toFixed(3)) : "—";
  const articles = sent?.article_count ?? 0;
  const ratio =
    typeof value === "number" ? Math.max(0, Math.min(1, (value + 1) / 2)) : 0.5;

  return (
    <div className="rounded-xl border border-white/[0.06] bg-bg-panel2/40 p-4">
      <div className="flex items-baseline justify-between">
        <h4 className="font-display text-sm font-semibold text-slate-100">{team}</h4>
        <span className="label">{(sent?.sentiment_label ?? "neutral").toString()}</span>
      </div>
      <div className="mt-3 flex items-baseline gap-3">
        <span className={`font-display text-3xl font-bold ${tone}`}>{text}</span>
        <span className="text-xs text-slate-500">avg sentiment</span>
      </div>

      <div className="mt-4 h-2 overflow-hidden rounded-full bg-white/[0.05]">
        <div
          className="h-full rounded-full bg-gradient-to-r from-loss/60 via-court/60 to-win/80"
          style={{ width: `${ratio * 100}%`, transition: "width 0.6s ease" }}
        />
      </div>

      <div className="mt-4 grid grid-cols-3 gap-2 text-center text-xs">
        <Cell label="Articles" value={articles} />
        <Cell label="Positive" value={sent?.positive_article_count ?? 0} tone="text-win" />
        <Cell label="Negative" value={sent?.negative_article_count ?? 0} tone="text-loss" />
      </div>
    </div>
  );
}

function Cell({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone?: string;
}) {
  return (
    <div className="rounded-lg border border-white/[0.05] bg-white/[0.02] py-2">
      <div className={`font-display text-base font-bold ${tone ?? "text-slate-100"}`}>{value}</div>
      <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
    </div>
  );
}
