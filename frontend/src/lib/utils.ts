import clsx, { ClassValue } from "clsx";

export function cn(...inputs: ClassValue[]): string {
  return clsx(inputs);
}

export function formatPct(value: number | undefined | null, digits = 0): string {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatSigned(value: number | undefined | null, digits = 1): string {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}`;
}

export function formatNumber(value: number | undefined | null, digits = 4): string {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  return value.toFixed(digits);
}

export function methodDisplayName(method: string): string {
  switch (method) {
    case "single_agent":
      return "Single Agent";
    case "multi_agent":
    case "multi_agent_debate":
      return "Multi-Agent Debate";
    case "cot":
    case "chain_of_thought":
      return "Chain-of-Thought";
    default:
      return method;
  }
}

export function methodAccent(method: string): string {
  switch (method) {
    case "single_agent":
      return "text-court-glow";
    case "multi_agent":
    case "multi_agent_debate":
      return "text-accent-glow";
    case "cot":
    case "chain_of_thought":
      return "text-win";
    default:
      return "text-slate-200";
  }
}

export function getPredictionBlock(report: {
  prediction?: { home_win_prob?: number; away_win_prob?: number; confidence?: string };
  synthesized_prediction?: { home_win_prob?: number; away_win_prob?: number; confidence?: string };
  agent_prediction?: { home_win_prob?: number; away_win_prob?: number; confidence?: string };
}): { home: number; away: number; confidence: string } {
  const pred =
    report.prediction ?? report.synthesized_prediction ?? report.agent_prediction ?? {};
  return {
    home: typeof pred.home_win_prob === "number" ? pred.home_win_prob : 0.5,
    away: typeof pred.away_win_prob === "number" ? pred.away_win_prob : 0.5,
    confidence: (pred.confidence ?? "medium").toString(),
  };
}

export function impactColor(impact: string): string {
  const lower = impact.toLowerCase();
  if (lower.includes("home")) return "text-win";
  if (lower.includes("away")) return "text-loss";
  return "text-court-glow";
}

export function impactLabel(impact: string): string {
  const lower = impact.toLowerCase();
  if (lower.includes("home")) return "Favors Home";
  if (lower.includes("away")) return "Favors Away";
  return "Mixed";
}

export function importanceWeight(importance: string): number {
  const lower = importance.toLowerCase();
  if (lower === "high") return 90;
  if (lower === "medium") return 60;
  return 35;
}

export function sentimentColor(value: number | undefined): string {
  if (typeof value !== "number") return "text-slate-300";
  if (value > 0.05) return "text-win";
  if (value < -0.05) return "text-loss";
  return "text-court-glow";
}

export function downloadJson(filename: string, payload: unknown): void {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
