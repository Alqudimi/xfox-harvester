/** Settings — every anti-ban, scheduling and risk knob, plus system status. */

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  Cpu,
  Database,
  HardDrive,
  Save,
  ShieldCheck,
  Trash2,
  Wrench,
  XCircle,
} from "lucide-react";
import { api, type AppSettings, type SystemStatus } from "../../lib/api";
import { useI18n } from "../../i18n";
import { useAuth } from "../auth/authContext";
import { Card, CardTitle, SectionHeader } from "../../components/ui/card";
import { Button, Field, Input, Spinner, Switch } from "../../components/ui/primitives";
import { useToast } from "../../components/ui/toast";
import { ConfirmDialog } from "../../components/ui/dialog";
import { formatDuration } from "../../lib/format";

export function Settings() {
  const { t } = useI18n();
  const { hasRole } = useAuth();
  const toast = useToast();
  const queryClient = useQueryClient();
  const canManage = hasRole("admin");

  const settings = useQuery({ queryKey: ["settings"], queryFn: () => api.get<AppSettings>("/api/settings") });
  const status = useQuery({
    queryKey: ["system-status"],
    queryFn: () => api.get<SystemStatus>("/api/system/status"),
    refetchInterval: 20_000,
  });

  const [draft, setDraft] = useState<AppSettings | null>(null);
  const [purgeOpen, setPurgeOpen] = useState(false);
  const [purgeConfirm, setPurgeConfirm] = useState("");

  useEffect(() => {
    if (settings.data && draft === null) setDraft(settings.data);
  }, [settings.data, draft]);

  const save = useMutation({
    mutationFn: () => api.put("/api/settings", draft),
    onSuccess: () => {
      toast.success(t("set.saved"));
      void queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: () => toast.error(t("common.unknownError")),
  });

  const maintenance = useMutation({
    mutationFn: () =>
      api.post<{ message: string; details: { events_removed: number; runs_removed: number } }>(
        "/api/system/maintenance/purge",
      ),
    onSuccess: (result) => {
      toast.success(
        t("set.maintenanceDone", {
          events: result.details?.events_removed ?? 0,
          runs: result.details?.runs_removed ?? 0,
        }),
      );
    },
    onError: () => toast.error(t("common.unknownError")),
  });

  const purge = useMutation({
    mutationFn: () => api.delete("/api/system/data/posts?confirm=DELETE"),
    onSuccess: () => {
      setPurgeOpen(false);
      toast.success(t("set.purgeDone"));
    },
    onError: () => toast.error(t("common.unknownError")),
  });

  if (!draft) {
    return (
      <div className="flex justify-center py-16">
        <Spinner />
      </div>
    );
  }

  const setAntiBan = (key: keyof AppSettings["anti_ban"], value: number) =>
    setDraft({ ...draft, anti_ban: { ...draft.anti_ban, [key]: value } });

  return (
    <div className="space-y-6">
      <SectionHeader
        title={t("set.title")}
        subtitle={t("set.subtitle")}
        action={
          canManage && (
            <Button icon={<Save className="h-4 w-4" />} loading={save.isPending} onClick={() => save.mutate()}>
              {t("common.save")}
            </Button>
          )
        }
      />

      {/* System status */}
      <Card>
        <CardTitle>{t("set.systemStatus")}</CardTitle>
        {status.isLoading || !status.data ? (
          <Spinner />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <StatusChip
              icon={<Cpu className="h-4 w-4" />}
              label={t("set.crawlfox")}
              value={status.data.crawlfox_available ? t("set.installed") : t("set.missing")}
              ok={status.data.crawlfox_available}
            />
            <StatusChip
              icon={<ShieldCheck className="h-4 w-4" />}
              label={t("set.camoufox")}
              value={status.data.camoufox_fetched ? t("set.installed") : t("set.missing")}
              ok={status.data.camoufox_fetched}
            />
            <StatusChip
              icon={<Database className="h-4 w-4" />}
              label={t("set.database")}
              value={status.data.database_ok ? t("set.ok") : t("common.error")}
              ok={status.data.database_ok}
            />
            <StatusChip
              icon={<HardDrive className="h-4 w-4" />}
              label={t("set.disk")}
              value={status.data.disk_free_gb !== null ? `${status.data.disk_free_gb} GB` : "—"}
              ok={(status.data.disk_free_gb ?? 1) > 1}
            />
            <div className="text-xs text-ink-400">
              <span className="font-semibold">{t("set.version")}:</span> v{status.data.version}
            </div>
            <div className="text-xs text-ink-400">
              <span className="font-semibold">{t("set.environment")}:</span> {status.data.environment}
            </div>
            <div className="text-xs text-ink-400">
              <span className="font-semibold">{t("set.uptime")}:</span>{" "}
              {formatDuration(status.data.uptime_seconds * 1000)}
            </div>
            <div dir="ltr" className="truncate text-xs text-ink-400">
              <span className="font-semibold">{t("set.dataDir")}:</span> {status.data.data_dir}
            </div>
          </div>
        )}
      </Card>

      {/* Anti-ban */}
      <Card>
        <CardTitle>{t("set.antiBan")}</CardTitle>
        <p className="-mt-2 mb-4 text-xs text-ink-400">{t("set.antiBanDesc")}</p>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <NumberField
            label={t("set.minRunGap")}
            hint={t("set.minRunGapHint")}
            value={draft.anti_ban.min_run_gap_minutes}
            min={5}
            max={720}
            step={5}
            disabled={!canManage}
            onChange={(value) => setAntiBan("min_run_gap_minutes", value)}
          />
          <NumberField
            label={t("set.gapJitter")}
            hint={t("set.gapJitterHint")}
            value={Math.round(draft.anti_ban.gap_jitter_fraction * 100)}
            min={0}
            max={50}
            step={5}
            disabled={!canManage}
            onChange={(value) => setAntiBan("gap_jitter_fraction", value / 100)}
          />
          <NumberField
            label={t("set.globalMinGap")}
            hint={t("set.globalMinGapHint")}
            value={draft.anti_ban.global_min_gap_minutes}
            min={2}
            max={180}
            step={1}
            disabled={!canManage}
            onChange={(value) => setAntiBan("global_min_gap_minutes", value)}
          />
          <NumberField
            label={t("set.maxConcurrent")}
            hint={t("set.maxConcurrentHint")}
            value={draft.anti_ban.max_concurrent_runs}
            min={1}
            max={3}
            step={1}
            disabled={!canManage}
            onChange={(value) => setAntiBan("max_concurrent_runs", value)}
          />
          <NumberField
            label={t("set.maxRunsDaily")}
            value={draft.anti_ban.max_runs_per_account_per_day}
            min={1}
            max={48}
            step={1}
            disabled={!canManage}
            onChange={(value) => setAntiBan("max_runs_per_account_per_day", value)}
          />
          <NumberField
            label={t("set.runTimeout")}
            value={draft.anti_ban.run_timeout_minutes}
            min={5}
            max={120}
            step={5}
            disabled={!canManage}
            onChange={(value) => setAntiBan("run_timeout_minutes", value)}
          />
          <NumberField
            label={t("set.backoffBase")}
            value={draft.anti_ban.backoff_base_minutes}
            min={1}
            max={120}
            step={1}
            disabled={!canManage}
            onChange={(value) => setAntiBan("backoff_base_minutes", value)}
          />
          <NumberField
            label={t("set.backoffCap")}
            value={draft.anti_ban.backoff_cap_minutes}
            min={15}
            max={1440}
            step={15}
            disabled={!canManage}
            onChange={(value) => setAntiBan("backoff_cap_minutes", value)}
          />
          <NumberField
            label={t("set.rateLimitCooldown")}
            value={draft.anti_ban.rate_limit_cooldown_minutes}
            min={10}
            max={720}
            step={5}
            disabled={!canManage}
            onChange={(value) => setAntiBan("rate_limit_cooldown_minutes", value)}
          />
          <NumberField
            label={t("set.emptyCooldown")}
            value={draft.anti_ban.empty_result_cooldown_minutes}
            min={5}
            max={360}
            step={5}
            disabled={!canManage}
            onChange={(value) => setAntiBan("empty_result_cooldown_minutes", value)}
          />
          <NumberField
            label={t("set.errorCooldown")}
            value={draft.anti_ban.error_cooldown_minutes}
            min={5}
            max={360}
            step={5}
            disabled={!canManage}
            onChange={(value) => setAntiBan("error_cooldown_minutes", value)}
          />
        </div>

        <div className="mt-6 border-t border-ink-800 pt-5">
          <p className="mb-4 text-xs font-bold text-ink-200">{t("set.healthTitle")}</p>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <NumberField
              label={t("set.healthSuccess")}
              value={draft.anti_ban.health_on_success}
              min={0}
              max={20}
              step={1}
              disabled={!canManage}
              onChange={(value) => setAntiBan("health_on_success", value)}
            />
            <NumberField
              label={t("set.healthEmpty")}
              value={draft.anti_ban.health_on_empty}
              min={0}
              max={40}
              step={1}
              disabled={!canManage}
              onChange={(value) => setAntiBan("health_on_empty", value)}
            />
            <NumberField
              label={t("set.healthRateLimited")}
              value={draft.anti_ban.health_on_rate_limited}
              min={0}
              max={60}
              step={5}
              disabled={!canManage}
              onChange={(value) => setAntiBan("health_on_rate_limited", value)}
            />
            <NumberField
              label={t("set.healthError")}
              value={draft.anti_ban.health_on_error}
              min={0}
              max={60}
              step={5}
              disabled={!canManage}
              onChange={(value) => setAntiBan("health_on_error", value)}
            />
            <NumberField
              label={t("set.disableThreshold")}
              hint={t("set.disableThresholdHint")}
              value={draft.anti_ban.disable_health_threshold}
              min={0}
              max={50}
              step={5}
              disabled={!canManage}
              onChange={(value) => setAntiBan("disable_health_threshold", value)}
            />
            <NumberField
              label={t("set.authFailThreshold")}
              hint={t("set.authFailThresholdHint")}
              value={draft.anti_ban.auth_failure_disable_threshold}
              min={1}
              max={10}
              step={1}
              disabled={!canManage}
              onChange={(value) => setAntiBan("auth_failure_disable_threshold", value)}
            />
            <NumberField
              label={t("set.warmupRuns")}
              hint={t("set.warmupRunsHint")}
              value={draft.anti_ban.warmup_runs}
              min={0}
              max={20}
              step={1}
              disabled={!canManage}
              onChange={(value) => setAntiBan("warmup_runs", value)}
            />
          </div>
        </div>
      </Card>

      {/* Schedule + risk */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardTitle>{t("set.schedule")}</CardTitle>
          <p className="-mt-2 mb-4 text-xs text-ink-400">{t("set.scheduleDesc")}</p>
          <div className="space-y-4">
            <Switch
              checked={draft.schedule.enabled}
              onChange={(value) => setDraft({ ...draft, schedule: { ...draft.schedule, enabled: value } })}
              label={t("set.activeHoursEnabled")}
            />
            <div className="grid grid-cols-2 gap-3">
              <Field label={t("set.activeFrom")}>
                <Input
                  type="time"
                  disabled={!canManage || !draft.schedule.enabled}
                  value={draft.schedule.start}
                  onChange={(event) =>
                    setDraft({ ...draft, schedule: { ...draft.schedule, start: event.target.value } })
                  }
                />
              </Field>
              <Field label={t("set.activeTo")}>
                <Input
                  type="time"
                  disabled={!canManage || !draft.schedule.enabled}
                  value={draft.schedule.end}
                  onChange={(event) =>
                    setDraft({ ...draft, schedule: { ...draft.schedule, end: event.target.value } })
                  }
                />
              </Field>
            </div>
          </div>
        </Card>

        <Card>
          <CardTitle>{t("set.risk")}</CardTitle>
          <p className="-mt-2 mb-4 text-xs text-ink-400">{t("set.riskDesc")}</p>
          <div className="grid gap-4 sm:grid-cols-2">
            <NumberField
              label={t("set.riskWindow")}
              value={draft.risk.window_minutes}
              min={15}
              max={1440}
              step={15}
              disabled={!canManage}
              onChange={(value) => setDraft({ ...draft, risk: { ...draft.risk, window_minutes: value } })}
            />
            <NumberField
              label={t("set.yellowFailureRate")}
              value={Math.round(draft.risk.yellow_failure_rate * 100)}
              min={1}
              max={99}
              step={1}
              disabled={!canManage}
              onChange={(value) =>
                setDraft({ ...draft, risk: { ...draft.risk, yellow_failure_rate: value / 100 } })
              }
            />
            <NumberField
              label={t("set.redFailureRate")}
              value={Math.round(draft.risk.red_failure_rate * 100)}
              min={2}
              max={100}
              step={1}
              disabled={!canManage}
              onChange={(value) =>
                setDraft({ ...draft, risk: { ...draft.risk, red_failure_rate: value / 100 } })
              }
            />
            <NumberField
              label={t("set.redRateLimitCount")}
              value={draft.risk.red_rate_limited_count}
              min={2}
              max={50}
              step={1}
              disabled={!canManage}
              onChange={(value) =>
                setDraft({ ...draft, risk: { ...draft.risk, red_rate_limited_count: value } })
              }
            />
            <NumberField
              label={t("set.redAuthCount")}
              value={draft.risk.red_auth_expired_count}
              min={1}
              max={20}
              step={1}
              disabled={!canManage}
              onChange={(value) =>
                setDraft({ ...draft, risk: { ...draft.risk, red_auth_expired_count: value } })
              }
            />
            <NumberField
              label={t("set.autoResume")}
              hint={t("set.autoResumeHint")}
              value={draft.risk.auto_resume_minutes}
              min={0}
              max={720}
              step={5}
              disabled={!canManage}
              onChange={(value) =>
                setDraft({ ...draft, risk: { ...draft.risk, auto_resume_minutes: value } })
              }
            />
          </div>
        </Card>
      </div>

      {/* Crawler + retention */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardTitle>{t("set.crawler")}</CardTitle>
          <div className="space-y-4">
            <Switch
              checked={draft.crawler.headless}
              onChange={(value) => setDraft({ ...draft, crawler: { ...draft.crawler, headless: value } })}
              label={t("set.headless")}
            />
            <Switch
              checked={draft.crawler.keep_raw_items}
              onChange={(value) =>
                setDraft({ ...draft, crawler: { ...draft.crawler, keep_raw_items: value } })
              }
              label={t("set.keepRaw")}
            />
            <NumberField
              label={t("set.maxScrolls")}
              value={draft.crawler.default_max_scrolls}
              min={1}
              max={30}
              step={1}
              disabled={!canManage}
              onChange={(value) =>
                setDraft({ ...draft, crawler: { ...draft.crawler, default_max_scrolls: value } })
              }
            />
          </div>
        </Card>

        <Card>
          <CardTitle>{t("set.retention")}</CardTitle>
          <div className="grid gap-4 sm:grid-cols-2">
            <NumberField
              label={t("set.eventsDays")}
              value={draft.retention.events_days}
              min={1}
              max={365}
              step={1}
              disabled={!canManage}
              onChange={(value) =>
                setDraft({ ...draft, retention: { ...draft.retention, events_days: value } })
              }
            />
            <NumberField
              label={t("set.runsDays")}
              value={draft.retention.finished_runs_days}
              min={1}
              max={1095}
              step={1}
              disabled={!canManage}
              onChange={(value) =>
                setDraft({ ...draft, retention: { ...draft.retention, finished_runs_days: value } })
              }
            />
          </div>
        </Card>
      </div>

      {/* Maintenance + danger */}
      {canManage && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardTitle>{t("set.maintenance")}</CardTitle>
            <p className="-mt-2 mb-4 text-xs text-ink-400">{t("set.maintenanceDesc")}</p>
            <Button
              variant="secondary"
              icon={<Wrench className="h-4 w-4" />}
              loading={maintenance.isPending}
              onClick={() => maintenance.mutate()}
            >
              {t("set.runMaintenance")}
            </Button>
          </Card>

          <Card className="border-red-500/30">
            <CardTitle>{t("set.danger")}</CardTitle>
            <p className="-mt-2 mb-4 text-xs text-ink-400">{t("set.dangerDesc")}</p>
            <Button
              variant="danger"
              icon={<Trash2 className="h-4 w-4" />}
              onClick={() => setPurgeOpen(true)}
            >
              {t("set.purgeData")}
            </Button>
          </Card>
        </div>
      )}

      <ConfirmDialog
        open={purgeOpen}
        onClose={() => setPurgeOpen(false)}
        onConfirm={() => purgeConfirm === "DELETE" && purge.mutate()}
        title={t("set.danger")}
        message={`${t("set.dangerDesc")} — ${t("set.purgeConfirm")}: DELETE`}
        confirmLabel={t("common.confirm")}
        loading={purge.isPending}
      />
      {purgeOpen && (
        <div className="mx-auto max-w-md">
          <Input
            placeholder="DELETE"
            value={purgeConfirm}
            onChange={(event) => setPurgeConfirm(event.target.value)}
          />
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */

function NumberField({
  label,
  hint,
  value,
  min,
  max,
  step,
  disabled,
  onChange,
}: {
  label: string;
  hint?: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  disabled?: boolean;
  onChange: (value: number) => void;
}) {
  return (
    <Field label={label} hint={hint}>
      <Input
        type="number"
        min={min}
        max={max}
        step={step ?? 1}
        disabled={disabled}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </Field>
  );
}

function StatusChip({
  icon,
  label,
  value,
  ok,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  ok: boolean;
}) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-ink-800 bg-ink-900/60 px-3.5 py-3">
      <span className={ok ? "text-emerald-400" : "text-red-400"}>
        {ok ? <CheckCircle2 className="h-4 w-4" /> : <XCircle className="h-4 w-4" />}
      </span>
      <div>
        <p className="text-[10px] font-semibold text-ink-400">{label}</p>
        <p className="text-xs font-bold text-ink-100">{value}</p>
      </div>
      <span className="ms-auto text-ink-500">{icon}</span>
    </div>
  );
}
