/** Events — searchable history + live tail. */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity, Search } from "lucide-react";
import { api, type AppEvent } from "../../lib/api";
import { useI18n } from "../../i18n";
import { SectionHeader } from "../../components/ui/card";
import { Badge, Input, Select, Spinner } from "../../components/ui/primitives";
import { Pagination } from "../../components/ui/table";
import { useLiveEvents } from "../../lib/sse";
import { formatDateTime } from "../../lib/format";

const PAGE_SIZE = 30;

export function Events() {
  const { t } = useI18n();
  const [q, setQ] = useState("");
  const [level, setLevel] = useState("");
  const [category, setCategory] = useState("");
  const [page, setPage] = useState(1);
  const [liveEnabled, setLiveEnabled] = useState(true);

  const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
  if (q) params.set("q", q);
  if (level) params.set("level", level);
  if (category) params.set("category", category);

  const history = useQuery({
    queryKey: ["events", params.toString()],
    queryFn: () => api.get<{ items: AppEvent[]; total: number }>(`/api/events?${params.toString()}`),
    refetchInterval: 15_000,
  });

  const live = useLiveEvents({ enabled: liveEnabled });

  const levelTone = (value: string) =>
    value === "error" ? "red" : value === "warning" ? "amber" : value === "success" ? "green" : "blue";

  const renderEvent = (event: AppEvent, key: string) => (
    <div
      key={key}
      className="flex items-start gap-3 border-b border-ink-800/60 px-4 py-3 last:border-0 hover:bg-ink-800/30"
    >
      <div className="w-28 shrink-0">
        <Badge tone={levelTone(event.level)}>{t(`ev.level.${event.level}`)}</Badge>
      </div>
      <div className="w-24 shrink-0">
        <Badge tone="neutral">{t(`ev.category.${event.category}` as never)}</Badge>
      </div>
      <p className="min-w-0 flex-1 break-words text-xs leading-relaxed text-ink-200">{event.message}</p>
      <span className="w-36 shrink-0 text-end text-[10px] tabular-nums text-ink-500">
        {formatDateTime(event.ts)}
      </span>
    </div>
  );

  return (
    <div>
      <SectionHeader title={t("ev.title")} subtitle={t("ev.subtitle")} />

      {/* Live strip */}
      <div className="mb-4 overflow-hidden rounded-xl border border-ink-800 bg-ink-900/70">
        <div className="flex items-center justify-between border-b border-ink-800 px-4 py-2.5">
          <span className="flex items-center gap-2 text-xs font-bold text-ink-200">
            <Activity className="h-4 w-4 text-fox-400" />
            {t("dash.liveFeed")}
          </span>
          <button
            onClick={() => setLiveEnabled((enabled) => !enabled)}
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
          </button>
        </div>
        <div className="max-h-44 divide-y divide-ink-800/60 overflow-y-auto">
          {live.events.length === 0 ? (
            <p className="px-4 py-8 text-center text-xs text-ink-500">{t("ev.noEvents")}</p>
          ) : (
            live.events
              .slice(0, 20)
              .map((event, index) => renderEvent(event, `live-${event.id ?? index}`))
          )}
        </div>
      </div>

      {/* Filters */}
      <div className="mb-4 grid gap-2 sm:grid-cols-3">
        <div className="relative">
          <Search className="absolute top-1/2 h-4 w-4 -translate-y-1/2 text-ink-500 ltr:left-3 rtl:right-3" />
          <Input
            className="ps-9"
            placeholder={t("ev.searchPlaceholder")}
            value={q}
            onChange={(event) => {
              setQ(event.target.value);
              setPage(1);
            }}
          />
        </div>
        <Select
          value={level}
          onChange={(event) => {
            setLevel(event.target.value);
            setPage(1);
          }}
        >
          <option value="">{t("common.all")} — {t("common.status")}</option>
          <option value="info">{t("ev.level.info")}</option>
          <option value="success">{t("ev.level.success")}</option>
          <option value="warning">{t("ev.level.warning")}</option>
          <option value="error">{t("ev.level.error")}</option>
        </Select>
        <Select
          value={category}
          onChange={(event) => {
            setCategory(event.target.value);
            setPage(1);
          }}
        >
          <option value="">{t("common.all")}</option>
          {[
            "system",
            "security",
            "account",
            "job",
            "run",
            "data",
            "risk",
            "export",
          ].map((item) => (
            <option key={item} value={item}>
              {t(`ev.category.${item}` as never)}
            </option>
          ))}
        </Select>
      </div>

      {/* History */}
      {history.isLoading ? (
        <div className="flex justify-center py-12">
          <Spinner />
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-ink-800 bg-ink-900/70">
          {(history.data?.items ?? []).length === 0 ? (
            <p className="px-4 py-12 text-center text-xs text-ink-500">{t("ev.noEvents")}</p>
          ) : (
            (history.data?.items ?? []).map((event) => renderEvent(event, `his-${event.id}`))
          )}
        </div>
      )}

      <Pagination
        page={page}
        pageSize={PAGE_SIZE}
        total={history.data?.total ?? 0}
        onChange={setPage}
      />
    </div>
  );
}
