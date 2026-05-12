import { NavLink, Outlet } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Activity, BarChart3, Coins, Cpu, Database, Wifi, WifiOff } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { to: "/", label: "Matchup", icon: Activity, exact: true },
  { to: "/research", label: "Research", icon: BarChart3 },
  { to: "/simulation", label: "ROI Sim", icon: Coins },
  { to: "/data", label: "Data", icon: Database },
];

export default function Layout() {
  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: 60_000,
  });

  return (
    <div className="relative min-h-screen">
      {/* Subtle court grid texture */}
      <div className="pointer-events-none fixed inset-0 -z-10 bg-court-grid opacity-90" />
      <div className="pointer-events-none fixed inset-0 -z-10 [mask-image:radial-gradient(ellipse_at_top,black,transparent_70%)]">
        <div className="h-full w-full bg-[linear-gradient(rgba(255,255,255,0.04)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.04)_1px,transparent_1px)] bg-[size:60px_60px]" />
      </div>

      <header className="sticky top-0 z-30 border-b border-white/5 bg-bg/70 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-6 py-4">
          <NavLink to="/" className="group flex items-center gap-3">
            <Logo />
            <div>
              <div className="font-display text-lg font-bold tracking-tight text-slate-50">
                MatchOdds<span className="text-accent">.</span>AI
              </div>
              <div className="text-[10px] font-medium uppercase tracking-[0.22em] text-slate-500">
                NBA Matchup Intelligence
              </div>
            </div>
          </NavLink>

          <nav className="flex items-center gap-1 rounded-2xl border border-white/[0.06] bg-bg-panel/60 p-1 backdrop-blur-xl">
            {NAV_ITEMS.map(({ to, label, icon: Icon, exact }) => (
              <NavLink
                key={to}
                to={to}
                end={exact}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-2 rounded-xl px-3.5 py-2 text-sm font-semibold transition-all",
                    isActive
                      ? "bg-white/[0.07] text-slate-50 shadow-glow"
                      : "text-slate-400 hover:bg-white/[0.04] hover:text-slate-100",
                  )
                }
              >
                <Icon className="h-4 w-4" />
                <span className="hidden sm:inline">{label}</span>
              </NavLink>
            ))}
          </nav>

          <div className="hidden items-center gap-2 md:flex">
            <ModelPill ok={Boolean(health?.llm_configured)} label={health?.llm_label} />
          </div>
        </div>
        <div className="glow-divider mx-auto h-px max-w-7xl" />
      </header>

      <main className="mx-auto max-w-7xl px-6 py-8 pb-24">
        <Outlet />
      </main>

      <footer className="border-t border-white/5 py-8">
        <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-2 px-6 text-center text-xs text-slate-500 md:flex-row md:text-left">
          <span>
            MatchOdds AI · Research interface only · Not financial advice
          </span>
          <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-600">
            Columbia · STAT GR5293 · Spring 2026
          </span>
        </div>
      </footer>
    </div>
  );
}

function Logo() {
  return (
    <div className="relative flex h-10 w-10 items-center justify-center rounded-xl border border-white/10 bg-gradient-to-br from-accent/30 via-court/20 to-transparent shadow-ember">
      <svg viewBox="0 0 32 32" className="h-6 w-6">
        <defs>
          <linearGradient id="logo-gr" x1="0" y1="0" x2="32" y2="32">
            <stop offset="0" stopColor="#ff8c61" />
            <stop offset="1" stopColor="#60a5fa" />
          </linearGradient>
        </defs>
        <circle cx="16" cy="16" r="11" stroke="url(#logo-gr)" strokeWidth="1.6" fill="none" />
        <path
          d="M5 16h22M16 5v22M9 9l14 14M23 9 9 23"
          stroke="url(#logo-gr)"
          strokeWidth="1.2"
          strokeLinecap="round"
        />
      </svg>
    </div>
  );
}

function ModelPill({ ok, label }: { ok: boolean; label?: string }) {
  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-semibold",
        ok
          ? "border-win/30 bg-win/10 text-win"
          : "border-loss/30 bg-loss/10 text-loss",
      )}
    >
      {ok ? <Wifi className="h-3.5 w-3.5" /> : <WifiOff className="h-3.5 w-3.5" />}
      <Cpu className="h-3.5 w-3.5" />
      {label ?? (ok ? "Model online" : "No API key")}
    </div>
  );
}
