/** Jobs list + creation wizard entry. */

import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, ListChecks, Pause, Play, Plus, Zap } from "lucide-react";
import { api, type Job } from "../../lib/api";
import { useI18n } from "../../i18n";
import { useAuth } from "../auth/authContext";
import { EmptyState, SectionHeader } from "../../components/ui/card";
import { Badge, Button, Spinner } from "../../components/ui/primitives";
import { AggrBadge, TD, THead, TRow, TableWrap } from "../../components/ui/table";
import { ConfirmDialog } from "../../components/ui/dialog";
import { JobWizard } from "./JobWizard";
import { useToast } from "../../components/ui/toast";
import { formatDateTime } from "../../lib/format";

export function Jobs() {
  const { t } = useI18n();
  const { hasRole } = useAuth();
  const toast = useToast();
  const queryClient = useQueryClient();
  const canManage = hasRole("operator");

  const jobs = useQuery({
    queryKey: ["jobs"],
    queryFn: () => api.get<Job[]>("/api/jobs"),
    refetchInterval: 8_000,
  });

  const [wizardOpen, setWizardOpen] = useState(false);
  const [deleting, setDeleting] = useState<Job | null>(null);

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    void queryClient.invalidateQueries({ queryKey: ["overview"] });
  };

  const action = useMutation({
    mutationFn: ({ job, name }: { job: Job; name: string }) =>
      api.post(`/api/jobs/${job.id}/action`, { action: name }),
    onSuccess: (_result, variables) => {
      invalidate();
      if (variables.name === "run_now") toast.success(t("job.runQueued"));
    },
    onError: (error) =>
      toast.error(error instanceof Error && error.message === "run_already_active"
        ? t("job.runActiveExists")
        : t("common.unknownError")),
  });

  const remove = useMutation({
    mutationFn: (job: Job) => api.delete(`/api/jobs/${job.id}`),
    onSuccess: () => {
      setDeleting(null);
      invalidate();
      toast.success(t("common.success"));
    },
    onError: () => toast.error(t("common.unknownError")),
  });

  const rows = jobs.data ?? [];

  return (
    <div>
      <SectionHeader
        title={t("job.title")}
        subtitle={t("job.subtitle")}
        action={
          canManage && (
            <Button icon={<Plus className="h-4 w-4" />} onClick={() => setWizardOpen(true)}>
              {t("job.create")}
            </Button>
          )
        }
      />

      {jobs.isLoading ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : rows.length === 0 ? (
        <EmptyState
          icon={<ListChecks className="h-8 w-8" />}
          title={t("job.title")}
          description={t("job.subtitle")}
        />
      ) : (
        <TableWrap>
          <THead
            columns={[
              t("common.name"),
              t("common.type"),
              t("job.schedule"),
              t("job.aggressiveness"),
              t("common.status"),
              t("job.runs"),
              t("job.newItems"),
              t("job.nextRun"),
              canManage ? t("common.actions") : "",
            ]}
          />
          <tbody>
            {rows.map((job) => (
              <TRow key={job.id}>
                <TD>
                  <Link
                    to={`/jobs/${job.id}`}
                    className="font-bold text-fox-300 transition-colors hover:text-fox-200"
                  >
                    {job.name}
                  </Link>
                </TD>
                <TD>
                  <Badge tone="blue">{t(`job.type.${job.type}` as never)}</Badge>
                </TD>
                <TD className="text-xs text-ink-300">
                  <span className="inline-flex items-center gap-1.5">
                    <CalendarClock className="h-3.5 w-3.5 text-ink-500" />
                    {job.schedule.kind === "interval"
                      ? `${job.schedule.interval_minutes}${t("common.minutes_short")}`
                      : job.schedule.kind === "daily"
                        ? job.schedule.daily_at
                        : t("job.schedule.manual")}
                  </span>
                </TD>
                <TD>
                  <AggrBadge value={job.anti_ban.aggressiveness} />
                </TD>
                <TD>
                  <Badge tone={job.status === "active" ? "green" : "neutral"}>
                    {t(`job.status.${job.status}`)}
                  </Badge>
                </TD>
                <TD className="text-xs tabular-nums">{job.stats.total_runs ?? 0}</TD>
                <TD className="text-xs font-bold tabular-nums text-fox-300">{job.stats.items_new ?? 0}</TD>
                <TD className="text-xs text-ink-400">
                  {job.schedule.kind === "manual" ? "—" : formatDateTime(job.next_run_at)}
                </TD>
                {canManage && (
                  <TD>
                    <div className="flex items-center gap-1.5">
                      <Button
                        variant="ghost"
                        size="sm"
                        title={t("job.runNow")}
                        onClick={() => action.mutate({ job, name: "run_now" })}
                      >
                        <Zap className="h-4 w-4 text-fox-400" />
                      </Button>
                      {job.status === "active" ? (
                        <Button
                          variant="ghost"
                          size="sm"
                          title={t("job.pause")}
                          onClick={() => action.mutate({ job, name: "pause" })}
                        >
                          <Pause className="h-4 w-4" />
                        </Button>
                      ) : (
                        <Button
                          variant="ghost"
                          size="sm"
                          title={t("job.resume")}
                          onClick={() => action.mutate({ job, name: "resume" })}
                        >
                          <Play className="h-4 w-4 text-emerald-400" />
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-red-400 hover:bg-red-500/10"
                        onClick={() => setDeleting(job)}
                      >
                        ✕
                      </Button>
                    </div>
                  </TD>
                )}
              </TRow>
            ))}
          </tbody>
        </TableWrap>
      )}

      {canManage && (
        <JobWizard open={wizardOpen} onClose={() => setWizardOpen(false)} onDone={invalidate} />
      )}

      <ConfirmDialog
        open={deleting !== null}
        onClose={() => setDeleting(null)}
        onConfirm={() => deleting && remove.mutate(deleting)}
        title={t("common.delete")}
        message={t("job.deleteConfirm")}
        confirmLabel={t("common.delete")}
        loading={remove.isPending}
      />
    </div>
  );
}
