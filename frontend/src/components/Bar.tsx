import { cn } from "@/lib/utils";

interface Props {
  value: number; // 0..1
  tone?: "win" | "loss" | "court" | "accent";
  className?: string;
}

export function Bar({ value, tone = "court", className }: Props) {
  const safe = Math.max(0, Math.min(1, value));
  const colorMap = {
    win: "from-win/70 to-win",
    loss: "from-loss/70 to-loss",
    court: "from-court/70 to-court-glow",
    accent: "from-accent/80 to-accent-glow",
  };
  return (
    <div className={cn("h-2 w-full overflow-hidden rounded-full bg-white/[0.06]", className)}>
      <div
        className={cn("h-full rounded-full bg-gradient-to-r", colorMap[tone])}
        style={{
          width: `${safe * 100}%`,
          transition: "width 0.8s cubic-bezier(0.4,0,0.2,1)",
        }}
      />
    </div>
  );
}
