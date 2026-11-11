/** Dashboard — totals, 14-day chart, top authors, recent runs, live feed. */

import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  Activity,
  FolderOpen,
  ListChecks,
  PlayCircle,
  RefreshCw,
  UserSquare2,
  Users,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, type Overview } from "../../lib/api";
import { useI18n } from "../../i18n";
import { useAuth } from "../auth/authContext";
import { Card, CardTitle, SectionHeader, StatCard } from "../../components/ui/card";
import { Badge, Button, Skeleton } from "../../components/ui/primitives";
import { RunStatusBadge, RiskBadge } from "../../components/ui/table";
import { useLiveEvents } from "../../lib/sse";
import { formatCompact, formatRelative } from "../../lib/format";
import { useToast } from "../../components/ui/toast";

export function Dashboard() {
  const { t, lang } = useI18n();
  const { user, hasRole } = useAuth();
  const toast = useToast();

  const overview = useQuery({
    queryKey: ["overview"],
    queryFn: () => api.get<Overview>("/api/system/overview"),
    refetchInterval: 15_000,
  });

  const live = useLiveEvents({
    onEvent: (event) => {
      if (event.type === "risk_level_changed" || event.type === "engine_paused") {
        void overview.refetch();
      }
    },
  });

  const data = overview.data;
  const chartData = (data?.collection_14d ?? []).map((point) => ({
    date: new Date(point.date).toLocaleDateString(lang === "ar" ? "ar" : "en", {
      month: "numeric",
      day: "numeric",
    }),
    count: point.count,
  }));

  const acknowledge = async () => {
    try {
      await api.post("/api/system/risk/acknowledge");
      toast.success(t("common.success"));
      await overview.refetch();
    } catch {
      toast.error(t("common.unknownError"));
    }
  };

  if (!data) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 8 }).map((_, index) => (
          <Skeleton key={index} className="h-24" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <SectionHeader
        title={t("dash.hello", { name: user?.display_name || user?.username || "" })}
        subtitle={data.risk.paused ? t("dash.riskBanner.red") : undefined}
        action={
          data.risk.paused && hasRole("operator") ? (
            <Button icon={<RefreshCw className="h-4 w-4" />} onClick={() => void acknowledge()}>
              {t("dash.acknowledge")}
            </Button>
          ) : (
            <Button
              variant="secondary"
              icon={<RefreshCw className="h-4 w-4" />}
              onClick={() => void overview.refetch()}
            >
              {t("common.refresh")}
            </Button>
          )
        }
      />

      {/* Stat cards */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label={t("dash.totalPosts")}
          value={formatCompact(data.totals.posts)}
          icon={<FolderOpen className="h-5 w-5" />}
          tone="fox"
        />
        <StatCard
          label={t("dash.totalAuthors")}
          value={formatCompact(data.totals.authors)}
          icon={<Users className="h-5 w-5" />}
          tone="blue"
        />
        <StatCard
          label={t("dash.activeAccounts")}
          value={`${data.totals.accounts_active}/${data.totals.accounts_total}`}
          icon={<UserSquare2 className="h-5 w-5" />}
          tone="green"
          sub={
            data.totals.accounts_invalid > 0
              ? `${data.totals.accounts_invalid} ✕`
              : undefined
          }
        />
        <StatCard
          label={t("dash.activeJobs")}
          value={`${data.totals.jobs_active}/${data.totals.jobs_total}`}
          icon={<ListChecks className="h-5 w-5" />}
          tone="amber"
        />
      </div>

      {/* Today row */}
      <div className="grid gap-4 sm:grid-cols-3">
        <Card className="flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold text-ink-400">{t("dash.todayRuns")}</p>
            <p className="mt-1 text-xl font-extrabold text-white">{data.today.runs}</p>
          </div>
          <Activity className="h-5 w-5 text-ink-400" />
        </Card>
        <Card className="flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold text-ink-400">{t("dash.todaySuccess")}</p>
            <p className="mt-1 text-xl font-extrabold text-emerald-400">{data.today.successful_runs}</p>
          </div>
          <PlayCircle className="h-5 w-5 text-ink-400" />
        </Card>
        <Card className="flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold text-ink-400">{t("dash.todayItems")}</p>
            <p className="mt-1 text-xl font-extrabold text-fox-300">+{data.today.items_new}</p>
          </div>
          <FolderOpen className="h-5 w-5 text-ink-400" />
        </Card>
      </div>

      {/* Chart + live feed */}
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardTitle
            action={
              <Badge tone={data.risk.level === "green" ? "green" : data.risk.level === "yellow" ? "amber" : "red"}>
                <RiskBadge level={data.risk.level} />
              </Badge>
            }
          >
            {t("dash.collection14d")}
          </CardTitle>
          <div className="h-64" dir="ltr">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="harvest" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#f97316" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="#f97316" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#26272f" vertical={false} />
                <XAxis dataKey="date" tickLine={false} axisLine={false} interval="preserveStartEnd" />
                <YAxis tickLine={false} axisLine={false} width={32} allowDecimals={false} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#1d1e24",
                    border: "1px solid #34353f",
                    borderRadius: 10,
                    color: "#d8d9df",
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="count"
                  stroke="#f97316"
                  strokeWidth={2}
                  fill="url(#harvest)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card padded={false} className="flex flex-col">
          <div className="flex items-center justify-between border-b border-ink-800 px-5 py-4">
            <h3 className="text-sm font-bold text-ink-100">{t("dash.liveFeed")}</h3>
            <span
              className={`inline-flex items-center gap-1.5 text-[10px] font-bold ${
                live.connected ? "text-emerald-400" : "text-ink-400"
              }`}
            >
              <span
                className={`live-dot h-1.5 w-1.5 rounded-full ${live.connected ? "bg-emerald-400" : "bg-ink-500"}`}
              />
              {live.connected ? t("ev.live") : t("ev.paused")}
            </span>
          </div>
          <div className="max-h-72 flex-1 space-y-1.5 overflow-y-auto px-4 py-3">
            {live.events.length === 0 && (
              <p className="px-1 py-8 text-center text-xs text-ink-500">{t("ev.noEvents")}</p>
            )}
            {live.events.slice(0, 30).map((event, index) => (
              <div
                key={`${event.id ?? index}-${event.ts}`}
                className="flex items-start gap-2 rounded-lg px-2 py-1.5 hover:bg-ink-800/50"
              >
                <span
                  className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${
                    event.level === "error"
                      ? "bg-red-400"
                      : event.level === "warning"
                        ? "bg-amber-400"
                        : event.level === "success"
                          ? "bg-emerald-400"
                          : "bg-sky-400"
                  }`}
                />
                <div className="min-w-0">
                  <p className="break-words text-[11px] leading-snug text-ink-200">{event.message}</p>
                  <p className="text-[10px] text-ink-500">{formatRelative(event.ts)}</p>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Top authors + recent runs */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardTitle
            action={
              <Link to="/authors" className="text-[11px] font-semibold text-fox-300 hover:text-fox-200">
                {t("dash.viewAll")}
              </Link>
            }
          >
            {t("dash.topAuthors")}
          </CardTitle>
          <div className="space-y-2.5">
            {data.top_authors.length === 0 && (
              <p className="py-6 text-center text-xs text-ink-500">{t("dash.noData")}</p>
            )}
            {data.top_authors.map((author) => (
              <div key={author.username} className="flex items-center gap-3">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-ink-700 text-[11px] font-bold text-ink-200">
                  {author.username.slice(0, 2).toUpperCase()}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-bold text-ink-100">{author.nickname || author.username}</p>
                  <p className="truncate text-[11px] text-ink-400">@{author.username}</p>
                </div>
                <Badge tone="fox">{author.posts_count}</Badge>
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <CardTitle
            action={
              <Link to="/jobs" className="text-[11px] font-semibold text-fox-300 hover:text-fox-200">
                {t("dash.viewAll")}
              </Link>
            }
          >
            {t("dash.recentRuns")}
          </CardTitle>
          <div className="space-y-2">
            {data.recent_runs.length === 0 && (
              <p className="py-6 text-center text-xs text-ink-500">{t("dash.noData")}</p>
            )}
            {data.recent_runs.map((run) => (
              <div
                key={run.id}
                className="flex items-center justify-between gap-3 rounded-lg border border-ink-800 px-3 py-2.5"
              >
                <div className="min-w-0">
                  <p className="truncate text-xs font-bold text-ink-100">{run.job_name ?? `#${run.job_id}`}</p>
                  <p className="text-[11px] text-ink-400">
                    {run.account_label ?? "—"} · {formatRelative(run.finished_at ?? run.started_at)}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {run.items_new > 0 && <Badge tone="fox">+{run.items_new}</Badge>}
                  <RunStatusBadge status={run.status} />
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
