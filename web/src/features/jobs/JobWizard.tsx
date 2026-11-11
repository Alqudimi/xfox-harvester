/** Five-step job creation wizard. */

import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  Check,
  Newspaper,
  Radar,
  Search,
  UserSearch,
  Wand2,
} from "lucide-react";
import {
  api,
  type JobConfig,
  type JobType,
  type ScheduleSpec,
  type XAccount,
  type JobCreatePayload,
} from "../../lib/api";
import { useI18n } from "../../i18n";
import { Badge, Button, Field, Input, Select, Switch } from "../../components/ui/primitives";
import { Dialog } from "../../components/ui/dialog";
import { useToast } from "../../components/ui/toast";

const TYPE_ICONS: Record<JobType, React.ReactNode> = {
  search: <Search className="h-6 w-6" />,
  timeline: <Radar className="h-6 w-6" />,
  news: <Newspaper className="h-6 w-6" />,
  monitor: <UserSearch className="h-6 w-6" />,
  composite: <Wand2 className="h-6 w-6" />,
};

interface DraftState {
  name: string;
  type: JobType;
  keywords: string[];
  keywordInput: string;
  maxItemsPerKeyword: number;
  tabs: { forYou: boolean; following: boolean };
  maxItems: number;
  maxScrolls: number | null;
  newsEnabled: boolean;
  newsDetail: boolean;
  newsMaxItems: number;
  monitorUsers: string[];
  monitorInput: string;
  onlyNew: boolean;
  maxTweets: number;
  globalMax: number;
  schedule: ScheduleSpec;
  aggressiveness: "cautious" | "balanced" | "fast";
  accountId: string;
  priority: number;
}

const INITIAL: DraftState = {
  name: "",
  type: "search",
  keywords: [],
  keywordInput: "",
  maxItemsPerKeyword: 20,
  tabs: { forYou: true, following: false },
  maxItems: 20,
  maxScrolls: null,
  newsEnabled: false,
  newsDetail: false,
  newsMaxItems: 5,
  monitorUsers: [],
  monitorInput: "",
  onlyNew: true,
  maxTweets: 10,
  globalMax: 100,
  schedule: { kind: "manual" },
  aggressiveness: "balanced",
  accountId: "",
  priority: 5,
};

export function JobWizard({
  open,
  onClose,
  onDone,
}: {
  open: boolean;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t } = useI18n();
  const toast = useToast();
  const [step, setStep] = useState(1);
  const [draft, setDraft] = useState<DraftState>(INITIAL);

  const accounts = useQuery({
    queryKey: ["accounts"],
    queryFn: () => api.get<XAccount[]>("/api/accounts"),
    enabled: open,
  });

  const update = <K extends keyof DraftState>(key: K, value: DraftState[K]) =>
    setDraft((previous) => ({ ...previous, [key]: value }));

  const types: JobType[] = ["search", "timeline", "news", "monitor", "composite"];

  const canProceed = useMemo(() => {
    if (step === 1) return draft.name.trim().length > 0;
    if (step === 2) {
      if (draft.type === "search" && draft.keywords.length === 0) return false;
      if (draft.type === "monitor" && draft.monitorUsers.length === 0) return false;
      if (draft.type === "composite")
        return (
          draft.keywords.length > 0 ||
          draft.monitorUsers.length > 0 ||
          draft.tabs.forYou ||
          draft.tabs.following ||
          draft.newsEnabled
        );
      return true;
    }
    if (step === 3) {
      if (draft.schedule.kind === "interval") return (draft.schedule.interval_minutes ?? 0) >= 15;
      if (draft.schedule.kind === "daily") return Boolean(draft.schedule.daily_at);
      return true;
    }
    return true;
  }, [step, draft]);

  const payload = useMemo<JobCreatePayload>(() => {
    const config: JobConfig = {};
    const wantsSearch = draft.type === "search" || (draft.type === "composite" && draft.keywords.length > 0);
    const wantsTimeline =
      draft.type === "timeline" ||
      (draft.type === "composite" && (draft.tabs.forYou || draft.tabs.following));
    const wantsNews = draft.type === "news" || (draft.type === "composite" && draft.newsEnabled);
    const wantsMonitor =
      draft.type === "monitor" || (draft.type === "composite" && draft.monitorUsers.length > 0);

    if (wantsSearch)
      config.search = { keywords: draft.keywords, max_items_per_keyword: draft.maxItemsPerKeyword };
    if (wantsTimeline)
      config.timeline = [
        ...(draft.tabs.forYou
          ? [{ tab: "For you", max_items: draft.maxItems, max_scrolls: draft.maxScrolls }]
          : []),
        ...(draft.tabs.following
          ? [{ tab: "Following", max_items: draft.maxItems, max_scrolls: draft.maxScrolls }]
          : []),
      ];
    if (wantsNews) config.news = { detail: draft.newsDetail, max_items: draft.newsMaxItems };
    if (wantsMonitor)
      config.monitor = {
        users: draft.monitorUsers.map((username) => ({
          username,
          only_new: draft.onlyNew,
          max_tweets: draft.maxTweets,
        })),
        global_max: draft.globalMax,
      };

    return {
      name: draft.name.trim(),
      type: draft.type,
      config,
      schedule: draft.schedule,
      anti_ban: { aggressiveness: draft.aggressiveness },
      account_id: draft.accountId ? Number(draft.accountId) : null,
      priority: draft.priority,
    };
  }, [draft]);

  const create = useMutation({
    mutationFn: () => api.post("/api/jobs", payload),
    onSuccess: () => {
      onClose();
      setDraft(INITIAL);
      setStep(1);
      onDone();
      toast.success(t("job.createDone"));
    },
    onError: () => toast.error(t("common.unknownError")),
  });

  const steps = [t("job.wizardStep1"), t("job.wizardStep2"), t("job.wizardStep3"), t("job.wizardStep4"), t("job.wizardStep5")];

  const addKeyword = () => {
    const value = draft.keywordInput.trim();
    if (!value || draft.keywords.includes(value) || draft.keywords.length >= 20) return;
    update("keywords", [...draft.keywords, value]);
    update("keywordInput", "");
  };

  const addMonitorUser = () => {
    const value = draft.monitorInput.trim().replace(/^@/, "");
    if (!value || draft.monitorUsers.includes(value) || draft.monitorUsers.length >= 50) return;
    update("monitorUsers", [...draft.monitorUsers, value]);
    update("monitorInput", "");
  };

  return (
    <Dialog open={open} onClose={onClose} title={t("job.create")} wide>
      {/* Stepper */}
      <div className="mb-6 flex items-center gap-1.5">
        {steps.map((label, index) => {
          const number = index + 1;
          const active = step === number;
          const done = step > number;
          return (
            <button
              key={label}
              onClick={() => number < step && setStep(number)}
              className={`flex flex-1 flex-col items-center gap-1.5 ${number < step ? "cursor-pointer" : ""}`}
            >
              <span
                className={`flex h-7 w-7 items-center justify-center rounded-full border text-[11px] font-bold transition-colors ${
                  done
                    ? "border-emerald-500 bg-emerald-500/20 text-emerald-300"
                    : active
                      ? "border-fox-500 bg-fox-500/20 text-fox-300"
                      : "border-ink-600 bg-ink-800 text-ink-400"
                }`}
              >
                {done ? <Check className="h-3.5 w-3.5" /> : number}
              </span>
              <span
                className={`hidden text-[10px] font-semibold sm:block ${
                  active ? "text-fox-300" : "text-ink-500"
                }`}
              >
                {label}
              </span>
            </button>
          );
        })}
      </div>

      {/* Step 1 — type */}
      {step === 1 && (
        <div className="space-y-4">
          <Field label={t("job.name")}>
            <Input
              value={draft.name}
              onChange={(event) => update("name", event.target.value)}
              maxLength={120}
              autoFocus
            />
          </Field>
          <div className="grid gap-2.5 sm:grid-cols-2">
            {types.map((type) => (
              <button
                key={type}
                onClick={() => update("type", type)}
                className={`flex items-start gap-3 rounded-xl border p-4 text-start transition-colors ${
                  draft.type === type
                    ? "border-fox-500 bg-fox-500/10"
                    : "border-ink-700 bg-ink-900 hover:border-ink-600"
                }`}
              >
                <span
                  className={`rounded-lg p-2 ${
                    draft.type === type ? "bg-fox-500/20 text-fox-300" : "bg-ink-800 text-ink-400"
                  }`}
                >
                  {TYPE_ICONS[type]}
                </span>
                <span>
                  <span className="block text-sm font-bold text-ink-100">{t(`job.type.${type}`)}</span>
                  <span className="mt-0.5 block text-[11px] leading-relaxed text-ink-400">
                    {t(`job.type.${type}Desc`)}
                  </span>
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Step 2 — config */}
      {step === 2 && (
        <div className="max-h-[60vh] space-y-4 overflow-y-auto pe-1">
          {(draft.type === "search" || draft.type === "composite") && (
            <div className="space-y-3 rounded-xl border border-ink-700 p-4">
              <Field label={t("job.keywords")} hint={t("job.keywordsHint")}>
                <div className="flex gap-2">
                  <Input
                    value={draft.keywordInput}
                    onChange={(event) => update("keywordInput", event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                        addKeyword();
                      }
                    }}
                  />
                  <Button variant="secondary" size="md" onClick={addKeyword}>
                    {t("common.add")}
                  </Button>
                </div>
              </Field>
              {draft.keywords.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {draft.keywords.map((keyword) => (
                    <button
                      key={keyword}
                      onClick={() => update("keywords", draft.keywords.filter((item) => item !== keyword))}
                      className="group inline-flex items-center gap-1.5 rounded-lg border border-ink-600 bg-ink-800 px-2.5 py-1 text-xs font-semibold text-ink-200 hover:border-red-500/50 hover:text-red-300"
                    >
                      {keyword}
                      <span className="text-ink-500 group-hover:text-red-400">✕</span>
                    </button>
                  ))}
                </div>
              )}
              <Field label={t("job.maxItemsPerKeyword")}>
                <Input
                  type="number"
                  min={1}
                  max={200}
                  value={draft.maxItemsPerKeyword}
                  onChange={(event) => update("maxItemsPerKeyword", Number(event.target.value))}
                />
              </Field>
            </div>
          )}

          {(draft.type === "timeline" || draft.type === "composite") && (
            <div className="space-y-3 rounded-xl border border-ink-700 p-4">
              <p className="text-xs font-bold text-ink-200">{t("job.tabs")}</p>
              <div className="flex flex-wrap gap-4">
                <Switch
                  checked={draft.tabs.forYou}
                  onChange={(value) => update("tabs", { ...draft.tabs, forYou: value })}
                  label={t("job.tab.forYou")}
                />
                <Switch
                  checked={draft.tabs.following}
                  onChange={(value) => update("tabs", { ...draft.tabs, following: value })}
                  label={t("job.tab.following")}
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Field label={t("job.maxItems")}>
                  <Input
                    type="number"
                    min={1}
                    max={200}
                    value={draft.maxItems}
                    onChange={(event) => update("maxItems", Number(event.target.value))}
                  />
                </Field>
                <Field label={`${t("job.maxScrolls")} (${t("common.optional")})`}>
                  <Input
                    type="number"
                    min={1}
                    max={30}
                    value={draft.maxScrolls ?? ""}
                    onChange={(event) =>
                      update("maxScrolls", event.target.value ? Number(event.target.value) : null)
                    }
                  />
                </Field>
              </div>
            </div>
          )}

          {(draft.type === "news" || draft.type === "composite") && (
            <div className="space-y-3 rounded-xl border border-ink-700 p-4">
              {draft.type === "composite" && (
                <Switch
                  checked={draft.newsEnabled}
                  onChange={(value) => update("newsEnabled", value)}
                  label={t("job.type.news")}
                />
              )}
              {(draft.type === "news" || draft.newsEnabled) && (
                <>
                  <Field label={t("job.maxItems")}>
                    <Input
                      type="number"
                      min={1}
                      max={50}
                      value={draft.newsMaxItems}
                      onChange={(event) => update("newsMaxItems", Number(event.target.value))}
                    />
                  </Field>
                  <Switch
                    checked={draft.newsDetail}
                    onChange={(value) => update("newsDetail", value)}
                    label={t("job.newsDetail")}
                  />
                </>
              )}
            </div>
          )}

          {(draft.type === "monitor" || draft.type === "composite") && (
            <div className="space-y-3 rounded-xl border border-ink-700 p-4">
              <Field label={t("job.monitorUsers")}>
                <div className="flex gap-2">
                  <Input
                    dir="ltr"
                    placeholder="@username"
                    value={draft.monitorInput}
                    onChange={(event) => update("monitorInput", event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                        addMonitorUser();
                      }
                    }}
                  />
                  <Button variant="secondary" size="md" onClick={addMonitorUser}>
                    {t("common.add")}
                  </Button>
                </div>
              </Field>
              {draft.monitorUsers.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {draft.monitorUsers.map((username) => (
                    <button
                      key={username}
                      onClick={() =>
                        update("monitorUsers", draft.monitorUsers.filter((item) => item !== username))
                      }
                      className="group inline-flex items-center gap-1.5 rounded-lg border border-ink-600 bg-ink-800 px-2.5 py-1 text-xs font-semibold text-ink-200 hover:border-red-500/50 hover:text-red-300"
                    >
                      @{username}
                      <span className="text-ink-500 group-hover:text-red-400">✕</span>
                    </button>
                  ))}
                </div>
              )}
              <Switch
                checked={draft.onlyNew}
                onChange={(value) => update("onlyNew", value)}
                label={t("job.onlyNew")}
              />
              <div className="grid grid-cols-2 gap-3">
                <Field label={t("job.maxTweets")}>
                  <Input
                    type="number"
                    min={1}
                    max={100}
                    value={draft.maxTweets}
                    onChange={(event) => update("maxTweets", Number(event.target.value))}
                  />
                </Field>
                <Field label={t("job.globalMax")}>
                  <Input
                    type="number"
                    min={1}
                    max={1000}
                    value={draft.globalMax}
                    onChange={(event) => update("globalMax", Number(event.target.value))}
                  />
                </Field>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Step 3 — schedule */}
      {step === 3 && (
        <div className="space-y-4">
          <div className="grid gap-2.5 sm:grid-cols-3">
            {(["manual", "interval", "daily"] as const).map((kind) => (
              <button
                key={kind}
                onClick={() => update("schedule", { kind })}
                className={`rounded-xl border p-3.5 text-start transition-colors ${
                  draft.schedule.kind === kind
                    ? "border-fox-500 bg-fox-500/10"
                    : "border-ink-700 bg-ink-900 hover:border-ink-600"
                }`}
              >
                <span className="block text-xs font-bold text-ink-100">{t(`job.schedule.${kind}`)}</span>
              </button>
            ))}
          </div>
          {draft.schedule.kind === "interval" && (
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label={t("job.intervalMinutes")} hint={t("job.intervalHint")}>
                <Input
                  type="number"
                  min={15}
                  max={10080}
                  value={draft.schedule.interval_minutes ?? 60}
                  onChange={(event) =>
                    update("schedule", { ...draft.schedule, interval_minutes: Number(event.target.value) })
                  }
                />
              </Field>
              <Field label={t("job.priority")}>
                <Input
                  type="number"
                  min={1}
                  max={10}
                  value={draft.priority}
                  onChange={(event) => update("priority", Number(event.target.value))}
                />
              </Field>
            </div>
          )}
          {draft.schedule.kind === "daily" && (
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label={t("job.dailyAt")}>
                <Input
                  type="time"
                  value={draft.schedule.daily_at ?? "08:00"}
                  onChange={(event) =>
                    update("schedule", { ...draft.schedule, daily_at: event.target.value })
                  }
                />
              </Field>
              <Field label={t("job.priority")}>
                <Input
                  type="number"
                  min={1}
                  max={10}
                  value={draft.priority}
                  onChange={(event) => update("priority", Number(event.target.value))}
                />
              </Field>
            </div>
          )}
          {draft.schedule.kind === "manual" && (
            <Field label={t("job.priority")}>
              <Input
                type="number"
                min={1}
                max={10}
                value={draft.priority}
                onChange={(event) => update("priority", Number(event.target.value))}
              />
            </Field>
          )}
        </div>
      )}

      {/* Step 4 — safety */}
      {step === 4 && (
        <div className="space-y-4">
          <div className="grid gap-2.5 sm:grid-cols-3">
            {(["cautious", "balanced", "fast"] as const).map((level) => (
              <button
                key={level}
                onClick={() => update("aggressiveness", level)}
                className={`rounded-xl border p-4 text-start transition-colors ${
                  draft.aggressiveness === level
                    ? level === "fast"
                      ? "border-amber-500 bg-amber-500/10"
                      : "border-fox-500 bg-fox-500/10"
                    : "border-ink-700 bg-ink-900 hover:border-ink-600"
                }`}
              >
                <span className="block text-sm font-bold text-ink-100">{t(`job.aggr.${level}`)}</span>
                <span className="mt-1 block text-[11px] leading-relaxed text-ink-400">
                  {t(`job.aggr.${level}Desc`)}
                </span>
              </button>
            ))}
          </div>
          <Field label={t("job.pinAccount")}>
            <Select
              value={draft.accountId}
              onChange={(event) => update("accountId", event.target.value)}
            >
              <option value="">{t("job.anyAccount")}</option>
              {(accounts.data ?? []).map((account) => (
                <option key={account.id} value={account.id}>
                  {account.label}
                </option>
              ))}
            </Select>
          </Field>
        </div>
      )}

      {/* Step 5 — review */}
      {step === 5 && (
        <div className="space-y-3">
          <p className="text-xs font-bold text-ink-200">{t("job.review")}</p>
          <div className="space-y-2 rounded-xl border border-ink-700 bg-ink-900 p-4 text-xs text-ink-300">
            <p>
              <span className="font-bold text-ink-100">{t("job.name")}:</span> {payload.name}
            </p>
            <p>
              <span className="font-bold text-ink-100">{t("common.type")}:</span>{" "}
              <Badge tone="blue">{t(`job.type.${draft.type}`)}</Badge>
            </p>
            <p dir="ltr" className="font-mono text-[10px] leading-relaxed text-ink-400">
              {JSON.stringify(payload.config, null, 2)}
            </p>
            <p>
              <span className="font-bold text-ink-100">{t("job.schedule")}:</span>{" "}
              {draft.schedule.kind === "interval"
                ? `${draft.schedule.interval_minutes} min`
                : draft.schedule.kind === "daily"
                  ? draft.schedule.daily_at
                  : t("job.schedule.manual")}
            </p>
            <p>
              <span className="font-bold text-ink-100">{t("job.aggressiveness")}:</span>{" "}
              {t(`job.aggr.${draft.aggressiveness}`)}
            </p>
          </div>
        </div>
      )}

      {/* Footer */}
      <div className="mt-6 flex items-center justify-between border-t border-ink-800 pt-4">
        <Button
          variant="ghost"
          size="sm"
          disabled={step === 1}
          onClick={() => setStep((current) => Math.max(1, current - 1))}
        >
          {t("common.previous")}
        </Button>
        {step < 5 ? (
          <Button
            size="sm"
            disabled={!canProceed}
            onClick={() => setStep((current) => Math.min(5, current + 1))}
          >
            {t("common.next")}
            <ArrowLeft className="h-4 w-4 rotate-180 rtl:rotate-0" />
          </Button>
        ) : (
          <Button size="sm" loading={create.isPending} onClick={() => create.mutate()}>
            <Check className="h-4 w-4" />
            {t("common.finish")}
          </Button>
        )}
      </div>
    </Dialog>
  );
}
