/** Data table primitives, pagination and semantic status chips. */

import type { ReactNode } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Badge } from "./primitives";
import { useI18n } from "../../i18n";

/* ---------------- Table ---------------- */

export function TableWrap({ children }: { children: ReactNode }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-ink-800 bg-ink-900/70">
      <table className="w-full min-w-[640px] border-collapse text-sm">{children}</table>
    </div>
  );
}

export function THead({ columns }: { columns: ReactNode[] }) {
  return (
    <thead>
      <tr className="border-b border-ink-800 bg-ink-850/60">
        {columns.map((column, index) => (
          <th
            key={index}
            className="px-4 py-3 text-start text-[11px] font-bold uppercase tracking-wide text-ink-400"
          >
            {column}
          </th>
        ))}
      </tr>
    </thead>
  );
}

export function TRow({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <tr className={`border-b border-ink-800/60 transition-colors last:border-0 hover:bg-ink-800/40 ${className}`}>
      {children}
    </tr>
  );
}

export function TD({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <td className={`px-4 py-3 align-middle text-ink-200 ${className}`}>{children}</td>;
}

/* ---------------- Pagination ---------------- */

export function Pagination({
  page,
  pageSize,
  total,
  onChange,
}: {
  page: number;
  pageSize: number;
  total: number;
  onChange: (page: number) => void;
}) {
  const { t } = useI18n();
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (pages <= 1) return null;

  const isRtl = document.documentElement.dir === "rtl";
  const PrevIcon = isRtl ? ChevronRight : ChevronLeft;
  const NextIcon = isRtl ? ChevronLeft : ChevronRight;

  return (
    <div className="mt-4 flex items-center justify-between gap-3">
      <span className="text-xs text-ink-400">{t("common.page", { page, total: pages })}</span>
      <div className="flex items-center gap-2">
        <button
          onClick={() => onChange(Math.max(1, page - 1))}
          disabled={page <= 1}
          className="rounded-lg border border-ink-700 p-1.5 text-ink-300 transition-colors hover:bg-ink-800 disabled:opacity-40"
          aria-label="previous page"
        >
          <PrevIcon className="h-4 w-4" />
        </button>
        <button
          onClick={() => onChange(Math.min(pages, page + 1))}
          disabled={page >= pages}
          className="rounded-lg border border-ink-700 p-1.5 text-ink-300 transition-colors hover:bg-ink-800 disabled:opacity-40"
          aria-label="next page"
        >
          <NextIcon className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}

/* ---------------- Semantic chips ---------------- */

export function HealthBar({ score }: { score: number }) {
  const tone = score >= 70 ? "bg-emerald-500" : score >= 40 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-ink-700">
        <div className={`h-full rounded-full ${tone}`} style={{ width: `${Math.max(3, score)}%` }} />
      </div>
      <span className="text-xs font-semibold text-ink-300">{score}</span>
    </div>
  );
}

export function AccountStatusBadge({ status }: { status: string }) {
  const { t } = useI18n();
  const tone =
    status === "active" ? "green" : status === "cooldown" ? "amber" : status === "invalid" ? "red" : "neutral";
  return <Badge tone={tone}>{t(`acc.status.${status}` as never)}</Badge>;
}

export function RunStatusBadge({ status }: { status: string }) {
  const { t } = useI18n();
  const tone =
    status === "success"
      ? "green"
      : status === "running"
        ? "blue"
        : status === "queued"
          ? "neutral"
          : status === "empty"
            ? "amber"
            : "red";
  return <Badge tone={tone}>{t(`run.status.${status}` as never)}</Badge>;
}

export function RiskBadge({ level }: { level: "green" | "yellow" | "red" }) {
  const { t } = useI18n();
  const tone = level === "green" ? "green" : level === "yellow" ? "amber" : "red";
  return <Badge tone={tone}>{t(`risk.${level}`)}</Badge>;
}

export function AggrBadge({ value }: { value: string }) {
  const { t } = useI18n();
  const tone = value === "cautious" ? "green" : value === "balanced" ? "fox" : "amber";
  return <Badge tone={tone}>{t(`job.aggr.${value}` as never)}</Badge>;
}
