import type { ReactNode } from "react";

import { clsx } from "clsx";

interface PanelProps {
  title: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}

export function Panel({ title, action, children, className }: PanelProps) {
  return (
    <section className={clsx("rounded-md border border-line bg-panel shadow-surface", className)}>
      <div className="flex min-h-12 items-center justify-between gap-3 border-b border-line px-4">
        <h2 className="text-sm font-semibold text-ink">{title}</h2>
        {action}
      </div>
      <div className="p-4">{children}</div>
    </section>
  );
}
