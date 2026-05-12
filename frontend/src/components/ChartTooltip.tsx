import { TooltipProps } from "recharts";

interface ChartTooltipExtraProps {
  /** Format a payload entry's value. Receives (value, name, entry). */
  valueFormatter?: (value: any, name?: string, entry?: any) => string | [string, string];
  /** Format the X-axis label shown at the top. */
  labelFormatter?: (label: any) => string;
  /** Optional secondary header below the label (e.g. game id). */
  sublabel?: (payload: any[]) => string | null;
}

type Props = TooltipProps<any, any> & ChartTooltipExtraProps;

/**
 * Drop-in replacement for Recharts' default tooltip.
 *
 * Default tooltips bleed dark text onto a dark background; this version
 * uses a glassy panel with high-contrast typography, mono-font numerics,
 * and a coloured dot per series. Same `formatter` and `labelFormatter`
 * conventions, surfaced through `valueFormatter` / `labelFormatter`
 * props so callers don't have to write a full custom renderer.
 */
export function ChartTooltip(props: Props) {
  const { active, payload, label, valueFormatter, labelFormatter, sublabel } = props;
  if (!active || !payload || payload.length === 0) return null;

  const headerText =
    labelFormatter && label !== undefined && label !== null
      ? labelFormatter(label)
      : label !== undefined && label !== null && label !== ""
      ? String(label)
      : null;

  const sub = sublabel ? sublabel(payload) : null;

  return (
    <div
      role="tooltip"
      style={{
        background:
          "linear-gradient(180deg, rgba(20,30,52,0.97) 0%, rgba(13,20,36,0.97) 100%)",
        border: "1px solid rgba(255,255,255,0.18)",
        borderRadius: "12px",
        boxShadow:
          "0 18px 48px -12px rgba(0,0,0,0.65), 0 0 0 1px rgba(255,255,255,0.04) inset",
        padding: "10px 12px",
        backdropFilter: "blur(10px)",
        minWidth: 160,
        maxWidth: 320,
      }}
    >
      {headerText && (
        <div
          style={{
            color: "#f8fafc",
            fontSize: 12,
            fontWeight: 700,
            letterSpacing: 0.2,
            marginBottom: payload.length > 0 ? 6 : 0,
          }}
        >
          {headerText}
        </div>
      )}
      {sub && (
        <div
          style={{
            color: "rgba(248,250,252,0.6)",
            fontSize: 10,
            textTransform: "uppercase",
            letterSpacing: 1.4,
            marginBottom: 6,
          }}
        >
          {sub}
        </div>
      )}
      <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
        {payload.map((entry: any, i: number) => {
          const colour = entry.color || entry.fill || entry.stroke || "#60a5fa";

          let displayValue: any = entry.value;
          let displayName: string | undefined = entry.name;

          if (valueFormatter) {
            const result = valueFormatter(entry.value, entry.name, entry);
            if (Array.isArray(result)) {
              displayValue = result[0];
              displayName = result[1];
            } else {
              displayValue = result;
            }
          } else if (typeof displayValue === "number") {
            displayValue = Number.isInteger(displayValue)
              ? displayValue.toLocaleString()
              : displayValue.toFixed(4);
          }

          return (
            <li
              key={i}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 12,
                padding: "3px 0",
                fontSize: 12,
                lineHeight: 1.4,
              }}
            >
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 8,
                  color: "rgba(226,232,240,0.95)",
                  minWidth: 0,
                }}
              >
                <span
                  aria-hidden
                  style={{
                    width: 9,
                    height: 9,
                    borderRadius: 999,
                    background: colour,
                    boxShadow: `0 0 0 2px ${colour}33, 0 0 8px ${colour}66`,
                    flexShrink: 0,
                  }}
                />
                <span
                  style={{
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {displayName ?? "Value"}
                </span>
              </span>
              <span
                style={{
                  color: "#ffffff",
                  fontFamily:
                    "JetBrains Mono, ui-monospace, SFMono-Regular, monospace",
                  fontWeight: 600,
                  fontVariantNumeric: "tabular-nums",
                  whiteSpace: "nowrap",
                }}
              >
                {String(displayValue)}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
