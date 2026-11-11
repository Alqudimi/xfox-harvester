/** Card containers, stat cards and section headers. */

import type { ReactNode } from "react";

export function Card({
  children,
  className = "",
  padded = true,
}: {
  children: ReactNode;
  className?: string;
  padded?: boolean;
}) {
  return (
    <div
      className={`rounded-xl border border-ink-800 bg-ink-900/70 shadow-lg shadow-black/20 ${
        padded ? "p-5" : ""
      } ${className}`}
    >
      {children}
    </div>
  );
}

export function CardTitle({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-4 flex items-center justify-between gap-3">
      <h3 className="text-sm font-bold text-ink-100">{children}</h3>
      {action}
    </div>
  );
}

export function SectionHeader({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 className="text-xl font-extrabold text-white">{title}</h1>
        {subtitle && <p className="mt-1 max-w-2xl text-sm leading-relaxed text-ink-400">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function StatCard({
  label,
  value,
  icon,
  tone = "fox",
  sub,
}: {
  label: string;
  value: string | number;
  icon: ReactNode;
  tone?: "fox" | "green" | "amber" | "red" | "blue";
  sub?: string;
}) {
  const tones: Record<string, string> = {
    fox: "bg-fox-500/10 text-fox-400",
    green: "bg-emerald-500/10 text-emerald-400",
    amber: "bg-amber-500/10 text-amber-400",
    red: "bg-red-500/10 text-red-400",
    blue: "bg-sky-500/10 text-sky-400",
  };
  return (
    <div className="rounded-xl border border-ink-800 bg-ink-900/70 p-4 shadow-lg shadow-black/20">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-xs font-semibold text-ink-400">{label}</p>
          <p className="mt-1 text-2xl font-extrabold text-white">{value}</p>
          {sub && <p className="mt-0.5 text-[11px] text-ink-400">{sub}</p>}
        </div>
        <div className={`rounded-lg p-2.5 ${tones[tone]}`}>{icon}</div>
      </div>
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-ink-700 bg-ink-900/40 px-6 py-12 text-center">
      <div className="rounded-full bg-ink-800 p-3.5 text-ink-300">{icon}</div>
      <p className="text-sm font-bold text-ink-100">{title}</p>
      {description && <p className="max-w-md text-xs leading-relaxed text-ink-400">{description}</p>}
      {action}
    </div>
  );
}
