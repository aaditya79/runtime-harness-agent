import { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Panel({
  children,
  className,
  title,
  subtitle,
  action,
  pad = true,
}: {
  children: ReactNode;
  className?: string;
  title?: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
  pad?: boolean;
}) {
  return (
    <section className={cn("panel relative overflow-hidden", pad && "p-6", className)}>
      {(title || action) && (
        <header className="mb-4 flex items-start justify-between gap-3">
          <div>
            {typeof title === "string" ? <h3 className="subheading">{title}</h3> : title}
            {subtitle && <p className="body-muted mt-1">{subtitle}</p>}
          </div>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

export function PanelTitle({ children }: { children: ReactNode }) {
  return <h3 className="subheading">{children}</h3>;
}
