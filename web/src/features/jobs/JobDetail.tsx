/** Job detail — overview, run history, live log terminal. */

import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  Ban,
  CalendarClock,
  Pause,
  Play,
  ScrollText,
  Terminal,
  Zap,
} from "lucide-react";
import { api, type Job, type RunPage } from "../../lib/api";
import { useI18n } from "../../i18n";
import { useAuth } from "../auth/authContext";
import { Card } from "../../components/ui/card";
import { Badge, Button, Spinner } from "../../components/ui/primitives";
import { AggrBadge, RunStatusBadge, TD, THead, TRow } from "../../components/ui/table";
import { useLiveEvents } from "../../lib/sse";
import { useToast } from "../../components/ui/toast";
import { formatDateTime, formatDuration } from "../../lib/format";

export function JobDetail() {
  const { id } = useParams<{ id: string }>();
  const { t } = useI18n();
  const { hasRole } = useAuth();
  const toast = useToast();
  const queryClient = useQueryClient();
  const canManage = hasRole("operator");

  const job = useQuery({
    queryKey: ["job", id],
    queryFn: () => api.get<Job>(`/api/jobs/${id}`),
    refetchInterval: 8_000,
  });

  const runs = useQuery({
    queryKey: ["job-runs", id],
    queryFn: () => api.get<RunPage>(`/api/jobs/${id}/runs?page=1&page_size=25`),
    refetchInterval: 5_000,
  });

  const [selectedRun, setSelectedRun] = useState<number | null>(null);
  const live = useLiveEvents({
    category: "run",
    onEvent: (event) => {
      if (event.run_id) setSelectedRun(event.run_id);
    },
  });

  const liveLogLines = useMemo(
    () =>
      live.events
        .filter((event) => event.type === "run_log" && event.run_id === selectedRun)
        .map((event) => event.message)
        .reverse(),
    [live.events, selectedRun],
  );

  const activeRun = (runs.data?.items ?? []).find(
    (run) => run.status === "running" || run.status === "queued",
  );

  const action = useMutation({
    mutationFn: (name: string) => api.post(`/api/jobs/${id}/action`, { action: name }),
    onSuccess: (_result, name) => {
      void queryClient.invalidateQueries({ queryKey: ["job", id] });
      void queryClient.invalidateQueries({ queryKey: ["job-runs", id] });
      if (name === "run_now") toast.success(t("job.runQueued"));
    },
    onError: (error) =>
      toast.error(
        error instanceof Error && error.message === "run_already_active"
          ? t("job.runActiveExists")
          : t("common.unknownError"),
      ),
  });

  const cancelRun = useMutation({
    mutationFn: (runId: number) => api.post(`/api/runs/${runId}/cancel`),
    onSuccess: () => {
      toast.success(t("run.cancelled"));
      void queryClient.invalidateQueries({ queryKey: ["job-runs", id] });
    },
    onError: () => toast.error(t("common.unknownError")),
  });

  if (job.isLoading || !job.data) {
    return (
      <div className="flex justify-center py-16">
        <Spinner />
      </div>
    );
  }

  const data = job.data;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link
            to="/jobs"
            className="mb-2 inline-flex items-center gap-1.5 text-xs font-semibold text-ink-400 hover:text-fox-300"
          >
            {t("job.backToJobs")}
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
          <h1 className="text-xl font-extrabold text-white">{data.name}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Badge tone="blue">{t(`job.type.${data.type}`)}</Badge>
            <Badge tone={data.status === "active" ? "green" : "neutral"}>
              {t(`job.status.${data.status}`)}
            </Badge>
            <AggrBadge value={data.anti_ban.aggressiveness} />
            <span className="inline-flex items-center gap-1.5 text-xs text-ink-400">
              <CalendarClock className="h-3.5 w-3.5" />
              {data.schedule.kind === "interval"
                ? `${data.schedule.interval_minutes} ${t("common.minutes_short")}`
                : data.schedule.kind === "daily"
                  ? data.schedule.daily_at
                  : t("job.schedule.manual")}
            </span>
          </div>
        </div>
        {canManage && (
          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              icon={<Zap className="h-4 w-4" />}
              onClick={() => action.mutate("run_now")}
              disabled={Boolean(activeRun)}
            >
              {t("job.runNow")}
            </Button>
            {data.status === "active" ? (
              <Button
                variant="secondary"
                size="sm"
                icon={<Pause className="h-4 w-4" />}
                onClick={() => action.mutate("pause")}
              >
                {t("job.pause")}
              </Button>
            ) : (
              <Button
                variant="secondary"
                size="sm"
                icon={<Play className="h-4 w-4" />}
                onClick={() => action.mutate("resume")}
              >
                {t("job.resume")}
              </Button>
            )}
            {activeRun && (
              <Button
                variant="danger"
                size="sm"
                icon={<Ban className="h-4 w-4" />}
                onClick={() => cancelRun.mutate(activeRun.id)}
              >
                {t("run.cancel")}
              </Button>
            )}
          </div>
        )}
      </div>

      {/* Stats row */}
      <div className="grid gap-4 sm:grid-cols-4">
        {[
          { label: t("job.runs"), value: data.stats.total_runs ?? 0 },
          { label: t("job.newItems"), value: data.stats.items_new ?? 0, tone: "text-fox-300" },
          {
            label: t("job.consecutiveFailures"),
            value: data.stats.consecutive_failures ?? 0,
            tone: (data.stats.consecutive_failures ?? 0) > 0 ? "text-red-400" : "",
          },
          { label: t("job.nextRun"), value: data.next_run_at ? formatDateTime(data.next_run_at) : "—" },
        ].map((item) => (
          <Card key={item.label} className="py-4">
            <p className="text-[11px] font-semibold text-ink-400">{item.label}</p>
            <p className={`mt-1 text-lg font-extrabold ${item.tone ?? "text-white"}`}>{item.value}</p>
          </Card>
        ))}
      </div>

      {/* Live log terminal */}
      {canManage && (
        <Card padded={false}>
          <div className="flex items-center justify-between border-b border-ink-800 px-5 py-3.5">
            <h3 className="flex items-center gap-2 text-sm font-bold text-ink-100">
              <Terminal className="h-4 w-4 text-fox-400" />
              {t("job.liveLog")}
              {selectedRun && <Badge tone="fox">#{selectedRun}</Badge>}
            </h3>
            <span
              className={`inline-flex items-center gap-1.5 text-[10px] font-bold ${
                live.connected ? "text-emerald-400" : "text-ink-400"
              }`}
            >
              <span
                className={`live-dot h-1.5 w-1.5 rounded-full ${
                  live.connected ? "bg-emerald-400" : "bg-ink-500"
                }`}
              />
              {live.connected ? t("ev.live") : t("ev.paused")}
            </span>
          </div>
          <div
            dir="ltr"
            className="max-h-64 overflow-y-auto bg-ink-950 px-4 py-3 font-mono text-[11px] leading-relaxed text-emerald-300/90"
          >
            {liveLogLines.length === 0 ? (
              <p className="text-ink-500">$ waiting for output…</p>
            ) : (
              liveLogLines.map((line, index) => (
                <p key={index} className="break-all">
                  {line}
                </p>
              ))
            )}
          </div>
        </Card>
      )}

      {/* Runs history */}
      <Card padded={false}>
        <div className="flex items-center justify-between border-b border-ink-800 px-5 py-3.5">
          <h3 className="flex items-center gap-2 text-sm font-bold text-ink-100">
            <ScrollText className="h-4 w-4 text-fox-400" />
            {t("job.runsHistory")}
          </h3>
          <span className="text-[11px] text-ink-400">{runs.data?.total ?? 0}</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[680px] text-sm">
            <THead
              columns={[
                "#",
                t("common.status"),
                t("run.items"),
                t("run.duration"),
                t("run.startedAt"),
                t("common.details"),
                "",
              ]}
            />
            <tbody>
              {(runs.data?.items ?? []).map((run) => (
                <TRow key={run.id}>
                  <TD className="font-mono text-xs text-ink-400">{run.id}</TD>
                  <TD>
                    <RunStatusBadge status={run.status} />
                  </TD>
                  <TD className="text-xs tabular-nums">
                    <span className="font-bold text-fox-300">+{run.items_new}</span>
                    <span className="text-ink-500"> / {run.items_total}</span>
                  </TD>
                  <TD className="text-xs tabular-nums">{formatDuration(run.duration_ms)}</TD>
                  <TD className="text-xs text-ink-400">{formatDateTime(run.started_at)}</TD>
                  <TD className="max-w-[280px]">
                    {run.outcome && (
                      <span className="block truncate text-[11px] text-ink-400" title={run.outcome.message ?? ""}>
                        {t(`run.outcome.${run.outcome.kind}` as never)}
                        {run.outcome.message ? ` — ${run.outcome.message}` : ""}
                      </span>
                    )}
                  </TD>
                  <TD>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setSelectedRun(run.id)}
                      className="text-[11px]"
                    >
                      {t("common.details")}
                    </Button>
                  </TD>
                </TRow>
              ))}
              {(runs.data?.items ?? []).length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-10 text-center text-xs text-ink-500">
                    {t("dash.noData")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Run log excerpt modal-less panel */}
      {selectedRun && (
        <RunLogPanel runId={selectedRun} onClose={() => setSelectedRun(null)} />
      )}
    </div>
  );
}

function RunLogPanel({ runId, onClose }: { runId: number; onClose: () => void }) {
  const { t } = useI18n();
  const log = useQuery({
    queryKey: ["run-log", runId],
    queryFn: () => api.get<{ content: string }>(`/api/runs/${runId}/log`),
    refetchInterval: (query) => (query.state.data?.content?.length ? 10_000 : 3_000),
  });

  return (
    <Card padded={false}>
      <div className="flex items-center justify-between border-b border-ink-800 px-5 py-3.5">
        <h3 className="text-sm font-bold text-ink-100">{t("run.logTitle", { id: runId })}</h3>
        <Button variant="ghost" size="sm" onClick={onClose}>
          ✕
        </Button>
      </div>
      <div
        dir="ltr"
        className="max-h-72 overflow-y-auto bg-ink-950 px-4 py-3 font-mono text-[11px] leading-relaxed text-ink-300"
      >
        {log.isLoading ? (
          <p className="text-ink-500">…</p>
        ) : (
          (log.data?.content ?? "—").split("\n").map((line, index) => (
            <p key={index} className="break-all">
              {line}
            </p>
          ))
        )}
      </div>
    </Card>
  );
}
