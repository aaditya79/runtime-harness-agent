import { Calendar, MapPin } from "lucide-react";

interface Props {
  homeTeam: string;
  awayTeam: string;
  homeAbbr: string;
  awayAbbr: string;
  homeLogo?: string;
  awayLogo?: string;
  date?: string; // pre-formatted
}

export function MatchupHeader({
  homeTeam,
  awayTeam,
  homeAbbr,
  awayAbbr,
  homeLogo,
  awayLogo,
  date,
}: Props) {
  return (
    <div className="panel relative overflow-hidden p-6">
      <div className="pointer-events-none absolute -right-12 -top-12 h-44 w-44 rounded-full bg-accent/15 blur-3xl" />
      <div className="pointer-events-none absolute -left-16 -bottom-12 h-48 w-48 rounded-full bg-court/15 blur-3xl" />

      <div className="grid grid-cols-1 items-center gap-4 md:grid-cols-[1fr_auto_1fr]">
        <TeamSide
          name={awayTeam}
          abbr={awayAbbr}
          logo={awayLogo}
          orientation="left"
          subtitle="Away"
        />

        <div className="relative flex h-full items-center justify-center">
          <div className="flex flex-col items-center gap-2">
            <div className="font-display text-xs font-bold uppercase tracking-[0.4em] text-slate-500">
              Tip-off
            </div>
            <div className="relative flex h-14 w-14 items-center justify-center rounded-full border border-white/10 bg-bg-panel2/80 shadow-glow">
              <span className="font-display text-base font-bold uppercase text-slate-300">@</span>
              <span className="absolute h-16 w-16 animate-pulse-dot rounded-full border border-accent/30" />
            </div>
            {date && (
              <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wider text-slate-500">
                <Calendar className="h-3 w-3" />
                {date}
              </div>
            )}
          </div>
        </div>

        <TeamSide
          name={homeTeam}
          abbr={homeAbbr}
          logo={homeLogo}
          orientation="right"
          subtitle="Home"
          accent
        />
      </div>
    </div>
  );
}

function TeamSide({
  name,
  abbr,
  logo,
  orientation,
  subtitle,
  accent,
}: {
  name: string;
  abbr: string;
  logo?: string;
  orientation: "left" | "right";
  subtitle: string;
  accent?: boolean;
}) {
  const isRight = orientation === "right";
  return (
    <div
      className={`flex items-center gap-4 ${isRight ? "justify-end text-right md:justify-end" : "justify-start text-left"}`}
    >
      {!isRight && (
        <Logo logo={logo} abbr={abbr} accent={accent} />
      )}
      <div>
        <div className={`flex items-center gap-2 text-[10px] uppercase tracking-[0.22em] ${accent ? "text-accent" : "text-slate-500"}`}>
          <MapPin className="h-3 w-3" />
          {subtitle}
        </div>
        <div className="font-display text-2xl font-bold tracking-tight text-slate-50">{name}</div>
        <div className="font-mono text-xs uppercase text-slate-500">{abbr}</div>
      </div>
      {isRight && (
        <Logo logo={logo} abbr={abbr} accent={accent} />
      )}
    </div>
  );
}

function Logo({ logo, abbr, accent }: { logo?: string; abbr: string; accent?: boolean }) {
  return (
    <div
      className={`relative flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl border ${accent ? "border-accent/40 bg-accent/10 shadow-ember" : "border-white/10 bg-white/[0.04]"}`}
    >
      {logo ? (
        <img src={logo} alt={abbr} className="h-12 w-12 object-contain" />
      ) : (
        <span className="font-display text-base font-bold text-slate-200">{abbr}</span>
      )}
    </div>
  );
}
