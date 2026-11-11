/** Authors directory. */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Users } from "lucide-react";
import { api, type AuthorPage } from "../../lib/api";
import { useI18n } from "../../i18n";
import { EmptyState, SectionHeader } from "../../components/ui/card";
import { Badge, Input, Spinner } from "../../components/ui/primitives";
import { Pagination, TD, THead, TRow, TableWrap } from "../../components/ui/table";
import { formatRelative } from "../../lib/format";

export function Authors() {
  const { t } = useI18n();
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);

  const authors = useQuery({
    queryKey: ["authors", q, page],
    queryFn: () =>
      api.get<AuthorPage>(
        `/api/data/authors?q=${encodeURIComponent(q)}&page=${page}&page_size=25`,
      ),
    placeholderData: (previous) => previous,
  });

  const rows = authors.data?.items ?? [];

  return (
    <div>
      <SectionHeader title={t("author.title")} subtitle={t("author.subtitle")} />

      <div className="mb-4 max-w-md">
        <Input
          placeholder={t("author.searchPlaceholder")}
          value={q}
          onChange={(event) => {
            setQ(event.target.value);
            setPage(1);
          }}
        />
      </div>

      {authors.isLoading ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : rows.length === 0 ? (
        <EmptyState icon={<Users className="h-8 w-8" />} title={t("author.title")} />
      ) : (
        <>
          <TableWrap>
            <THead
              columns={[
                t("author.username"),
                t("author.nickname"),
                t("author.postsCount"),
                t("author.firstSeen"),
                t("author.lastSeen"),
                "",
              ]}
            />
            <tbody>
              {rows.map((author) => (
                <TRow key={author.username}>
                  <TD>
                    <span dir="ltr" className="font-mono text-xs font-bold text-fox-300">
                      @{author.username}
                    </span>
                  </TD>
                  <TD className="text-xs">{author.nickname ?? "—"}</TD>
                  <TD>
                    <Badge tone="fox">{author.posts_count}</Badge>
                  </TD>
                  <TD className="text-[11px] text-ink-400">{formatRelative(author.first_seen)}</TD>
                  <TD className="text-[11px] text-ink-400">{formatRelative(author.last_seen)}</TD>
                  <TD>
                    {author.profile_url && (
                      <a
                        href={author.profile_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-[11px] font-semibold text-ink-400 hover:text-fox-300"
                      >
                        X ↗
                      </a>
                    )}
                  </TD>
                </TRow>
              ))}
            </tbody>
          </TableWrap>
          <Pagination
            page={page}
            pageSize={25}
            total={authors.data?.total ?? 0}
            onChange={setPage}
          />
        </>
      )}
    </div>
  );
}
