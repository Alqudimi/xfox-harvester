/** Harvested posts explorer — filters, sorting, export. */

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Download, ExternalLink, Filter, FolderOpen, RefreshCw, Search } from "lucide-react";
import { api, type ExportRow, type PostFilterState, type PostPage } from "../../lib/api";
import { useI18n } from "../../i18n";
import { useAuth } from "../auth/authContext";
import { EmptyState, SectionHeader } from "../../components/ui/card";
import { Badge, Button, Field, Input, Select, Spinner } from "../../components/ui/primitives";
import { Pagination, TD, THead, TRow, TableWrap } from "../../components/ui/table";
import { Dialog } from "../../components/ui/dialog";
import { useToast } from "../../components/ui/toast";
import { formatCompact, formatDateTime, formatRelative } from "../../lib/format";

const DEFAULT_FILTERS: PostFilterState = {
  sort: "publish_time",
  order: "desc",
  page: 1,
  page_size: 25,
};

export function Posts() {
  const { t } = useI18n();
  const { hasRole } = useAuth();
  const toast = useToast();
  const canExport = hasRole("operator");

  const [filters, setFilters] = useState<PostFilterState>(DEFAULT_FILTERS);
  const [searchInput, setSearchInput] = useState("");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);

  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  });
  if (filters.q) params.set("q", filters.q);
  if (searchInput && !filters.q) params.set("q", searchInput);

  const posts = useQuery({
    queryKey: ["posts", params.toString()],
    queryFn: () => api.get<PostPage>(`/api/data/posts?${params.toString()}`),
    placeholderData: (previous) => previous,
  });

  const sources = useQuery({
    queryKey: ["sources"],
    queryFn: () => api.get<string[]>("/api/data/sources"),
  });

  const exportsList = useQuery({
    queryKey: ["exports"],
    queryFn: () => api.get<ExportRow[]>("/api/exports"),
    refetchInterval: 10_000,
    enabled: canExport,
  });

  const createExport = useMutation({
    mutationFn: (format: string) =>
      api.post("/api/exports", {
        entity: "posts",
        format,
        filters: { ...filters, q: searchInput || filters.q },
      }),
    onSuccess: () => {
      setExportOpen(false);
      toast.success(t("post.exportStarted"));
      void exportsList.refetch();
    },
    onError: () => toast.error(t("common.unknownError")),
  });

  const update = <K extends keyof PostFilterState>(key: K, value: PostFilterState[K]) =>
    setFilters((previous) => ({ ...previous, [key]: value, page: 1 }));

  const totalPages = posts.data ? Math.ceil(posts.data.total / filters.page_size) : 0;

  return (
    <div>
      <SectionHeader
        title={t("post.title")}
        subtitle={t("post.subtitle")}
        action={
          <div className="flex items-center gap-2">
            {canExport && (
              <Button
                variant="secondary"
                size="sm"
                icon={<Download className="h-4 w-4" />}
                onClick={() => setExportOpen(true)}
              >
                {t("post.export")}
              </Button>
            )}
          </div>
        }
      />

      {/* Search bar */}
      <div className="mb-4 flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute top-1/2 h-4 w-4 -translate-y-1/2 text-ink-500 ltr:left-3 rtl:right-3" />
          <Input
            className="ps-9"
            placeholder={t("post.searchPlaceholder")}
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") update("q", searchInput);
            }}
          />
        </div>
        <Button
          variant={filtersOpen ? "primary" : "outline"}
          size="md"
          icon={<Filter className="h-4 w-4" />}
          onClick={() => setFiltersOpen((open) => !open)}
        >
          {t("post.filters")}
        </Button>
      </div>

      {/* Filter panel */}
      {filtersOpen && (
        <div className="page-enter mb-4 grid gap-3 rounded-xl border border-ink-800 bg-ink-900/70 p-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field label={t("post.author")}>
            <Input
              dir="ltr"
              placeholder="@username"
              value={filters.author ?? ""}
              onChange={(event) => update("author", event.target.value || undefined)}
            />
          </Field>
          <Field label={t("post.source")}>
            <Select
              value={filters.sources?.[0] ?? ""}
              onChange={(event) => update("sources", event.target.value ? [event.target.value] : undefined)}
            >
              <option value="">{t("common.all")}</option>
              {(sources.data ?? []).map((source) => (
                <option key={source} value={source}>
                  {source}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={t("post.dateFrom")}>
            <Input
              type="date"
              value={filters.date_from?.slice(0, 10) ?? ""}
              onChange={(event) => update("date_from", event.target.value || undefined)}
            />
          </Field>
          <Field label={t("post.dateTo")}>
            <Input
              type="date"
              value={filters.date_to?.slice(0, 10) ?? ""}
              onChange={(event) => update("date_to", event.target.value || undefined)}
            />
          </Field>
          <Field label={t("post.minLikes")}>
            <Input
              type="number"
              min={0}
              value={filters.min_likes ?? ""}
              onChange={(event) => update("min_likes", event.target.value ? Number(event.target.value) : undefined)}
            />
          </Field>
          <Field label={t("post.minViews")}>
            <Input
              type="number"
              min={0}
              value={filters.min_views ?? ""}
              onChange={(event) => update("min_views", event.target.value ? Number(event.target.value) : undefined)}
            />
          </Field>
          <Field label={t("post.hasMedia")}>
            <Select
              value={filters.has_media === undefined ? "" : String(filters.has_media)}
              onChange={(event) =>
                update("has_media", event.target.value === "" ? undefined : event.target.value === "true")
              }
            >
              <option value="">{t("common.all")}</option>
              <option value="true">{t("post.withMedia")}</option>
              <option value="false">{t("post.withoutMedia")}</option>
            </Select>
          </Field>
          <Field label={t("post.sort")}>
            <div className="flex gap-2">
              <Select
                value={filters.sort}
                onChange={(event) => update("sort", event.target.value as PostFilterState["sort"])}
              >
                <option value="publish_time">{t("post.sort.publish_time")}</option>
                <option value="likes">{t("post.sort.likes")}</option>
                <option value="views">{t("post.sort.views")}</option>
                <option value="crawl_time">{t("post.sort.crawl_time")}</option>
              </Select>
              <Select
                value={filters.order}
                onChange={(event) => update("order", event.target.value as PostFilterState["order"])}
              >
                <option value="desc">↓</option>
                <option value="asc">↑</option>
              </Select>
            </div>
          </Field>
          <div className="flex items-end">
            <Button
              variant="ghost"
              size="sm"
              icon={<RefreshCw className="h-3.5 w-3.5" />}
              onClick={() => {
                setFilters(DEFAULT_FILTERS);
                setSearchInput("");
              }}
            >
              {t("post.resetFilters")}
            </Button>
          </div>
        </div>
      )}

      {/* Results */}
      {posts.isLoading ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : (posts.data?.items ?? []).length === 0 ? (
        <EmptyState icon={<FolderOpen className="h-8 w-8" />} title={t("post.noResults")} />
      ) : (
        <>
          <TableWrap>
            <THead
              columns={[
                t("post.author"),
                t("post.content"),
                t("post.likes"),
                t("post.views"),
                t("post.source"),
                t("post.publishTime"),
                "",
              ]}
            />
            <tbody>
              {(posts.data?.items ?? []).map((post) => (
                <TRow key={post.id}>
                  <TD>
                    <p className="max-w-[140px] truncate text-xs font-bold text-ink-100">
                      {post.author.nickname || post.author.username}
                    </p>
                    <p dir="ltr" className="max-w-[140px] truncate text-[11px] text-ink-400">
                      @{post.author.username}
                    </p>
                  </TD>
                  <TD className="max-w-md">
                    <p className="line-clamp-2 text-xs leading-relaxed text-ink-200">{post.content}</p>
                    {post.media.length > 0 && (
                      <Badge tone="fox" className="mt-1">
                        {t("post.mediaCount", { count: post.media.length })}
                      </Badge>
                    )}
                  </TD>
                  <TD className="text-xs tabular-nums">{formatCompact(post.stats.likes)}</TD>
                  <TD className="text-xs tabular-nums">{formatCompact(post.stats.views)}</TD>
                  <TD>
                    <Badge tone="neutral">{post.source}</Badge>
                  </TD>
                  <TD className="text-[11px] text-ink-400">
                    {formatDateTime(post.publish_time)}
                    <span className="text-ink-600"> {formatRelative(post.crawl_time)}</span>
                  </TD>
                  <TD>
                    {post.url && (
                      <a
                        href={post.url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex rounded-lg p-1.5 text-ink-400 transition-colors hover:bg-ink-700 hover:text-fox-300"
                        title={t("post.openOnX")}
                      >
                        <ExternalLink className="h-4 w-4" />
                      </a>
                    )}
                  </TD>
                </TRow>
              ))}
            </tbody>
          </TableWrap>
          <Pagination
            page={filters.page}
            pageSize={filters.page_size}
            total={posts.data?.total ?? 0}
            onChange={(page) => setFilters((previous) => ({ ...previous, page }))}
          />
          <p className="mt-2 text-[11px] text-ink-500">
            {formatCompact(posts.data?.total ?? 0)} · {totalPages} pages
          </p>
        </>
      )}

      {/* Export dialog */}
      <Dialog open={exportOpen} onClose={() => setExportOpen(false)} title={t("post.exportTitle")}>
        <p className="mb-4 rounded-lg border border-ink-700 bg-ink-900 px-3 py-2 text-xs text-ink-300">
          {t("post.exportHint")}
        </p>
        <div className="grid grid-cols-3 gap-2">
          {(["csv", "json", "xlsx"] as const).map((format) => (
            <button
              key={format}
              disabled={createExport.isPending}
              onClick={() => createExport.mutate(format)}
              className="rounded-xl border border-ink-700 bg-ink-900 py-5 text-sm font-bold text-ink-100 transition-colors hover:border-fox-500 hover:text-fox-300 disabled:opacity-50"
            >
              {t(`post.format.${format}`)}
            </button>
          ))}
        </div>
      </Dialog>

      {/* Exports list */}
      {canExport && (exportsList.data ?? []).length > 0 && (
        <div className="mt-8">
          <h3 className="mb-3 text-sm font-bold text-ink-100">{t("ex.title")}</h3>
          <div className="space-y-2">
            {(exportsList.data ?? []).map((row) => (
              <div
                key={row.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-ink-800 bg-ink-900/60 px-4 py-3"
              >
                <div className="min-w-0">
                  <p dir="ltr" className="truncate font-mono text-xs text-ink-200">
                    {row.file_name ?? `export-${row.id}`}
                  </p>
                  <p className="text-[11px] text-ink-500">
                    {row.rows} {t("ex.rows")} · {formatDateTime(row.created_at)}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge
                    tone={row.status === "done" ? "green" : row.status === "failed" ? "red" : "amber"}
                  >
                    {t(`ex.status.${row.status}`)}
                  </Badge>
                  {row.status === "done" && (
                    <a href={`/api/exports/${row.id}/download`}>
                      <Button size="sm" icon={<Download className="h-3.5 w-3.5" />}>
                        {t("ex.download")}
                      </Button>
                    </a>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
