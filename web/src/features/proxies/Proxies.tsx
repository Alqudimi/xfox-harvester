/** Proxies — sticky per-account proxy pool with live checks. */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Globe, Plus, Wifi, WifiOff } from "lucide-react";
import { api, type Proxy } from "../../lib/api";
import { useI18n } from "../../i18n";
import { useAuth } from "../auth/authContext";
import { EmptyState, SectionHeader } from "../../components/ui/card";
import { Badge, Button, Field, Input, Spinner } from "../../components/ui/primitives";
import { TD, THead, TRow, TableWrap } from "../../components/ui/table";
import { ConfirmDialog, Dialog } from "../../components/ui/dialog";
import { useToast } from "../../components/ui/toast";
import { formatRelative } from "../../lib/format";

export function Proxies() {
  const { t } = useI18n();
  const { hasRole } = useAuth();
  const toast = useToast();
  const queryClient = useQueryClient();
  const canManage = hasRole("operator");

  const proxies = useQuery({
    queryKey: ["proxies"],
    queryFn: () => api.get<Proxy[]>("/api/proxies"),
  });

  const [addOpen, setAddOpen] = useState(false);
  const [deleting, setDeleting] = useState<Proxy | null>(null);
  const [checkingId, setCheckingId] = useState<number | null>(null);

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ["proxies"] });

  const remove = useMutation({
    mutationFn: (proxy: Proxy) => api.delete(`/api/proxies/${proxy.id}`),
    onSuccess: () => {
      setDeleting(null);
      invalidate();
      toast.success(t("common.success"));
    },
    onError: () => toast.error(t("common.unknownError")),
  });

  const check = async (proxy: Proxy) => {
    setCheckingId(proxy.id);
    try {
      const result = await api.post<{ ok: boolean; latency_ms: number | null; error: string | null }>(
        `/api/proxies/${proxy.id}/check`,
      );
      if (result.ok) toast.success(t("px.checkOk", { latency: result.latency_ms ?? "?" }));
      else toast.error(t("px.checkFailed", { error: result.error ?? "" }));
      invalidate();
    } catch {
      toast.error(t("common.unknownError"));
    } finally {
      setCheckingId(null);
    }
  };

  const rows = proxies.data ?? [];

  return (
    <div>
      <SectionHeader
        title={t("px.title")}
        subtitle={t("px.subtitle")}
        action={
          canManage && (
            <Button icon={<Plus className="h-4 w-4" />} onClick={() => setAddOpen(true)}>
              {t("px.add")}
            </Button>
          )
        }
      />

      {proxies.isLoading ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : rows.length === 0 ? (
        <EmptyState icon={<Globe className="h-8 w-8" />} title={t("px.title")} />
      ) : (
        <TableWrap>
          <THead
            columns={[
              t("common.name"),
              t("px.url"),
              t("common.status"),
              t("px.latency"),
              t("px.lastCheck"),
              canManage ? t("common.actions") : "",
            ]}
          />
          <tbody>
            {rows.map((proxy) => (
              <TRow key={proxy.id}>
                <TD className="font-bold">{proxy.label || "—"}</TD>
                <TD>
                  <span dir="ltr" className="font-mono text-xs text-ink-300">
                    {proxy.url}
                  </span>
                </TD>
                <TD>
                  <Badge tone={proxy.status === "active" ? "green" : "neutral"}>
                    {t(`px.status.${proxy.status}`)}
                  </Badge>
                </TD>
                <TD className="text-xs tabular-nums">
                  {proxy.latency_ms !== null ? `${proxy.latency_ms}ms` : "—"}
                </TD>
                <TD className="text-xs text-ink-400">{formatRelative(proxy.last_check_at)}</TD>
                {canManage && (
                  <TD>
                    <div className="flex items-center gap-1.5">
                      <Button
                        variant="ghost"
                        size="sm"
                        title={t("px.check")}
                        loading={checkingId === proxy.id}
                        onClick={() => void check(proxy)}
                      >
                        {proxy.latency_ms !== null ? (
                          <Wifi className="h-4 w-4 text-emerald-400" />
                        ) : (
                          <WifiOff className="h-4 w-4 text-ink-400" />
                        )}
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-red-400 hover:bg-red-500/10"
                        onClick={() => setDeleting(proxy)}
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

      <AddProxyDialog open={addOpen} onClose={() => setAddOpen(false)} onDone={invalidate} />

      <ConfirmDialog
        open={deleting !== null}
        onClose={() => setDeleting(null)}
        onConfirm={() => deleting && remove.mutate(deleting)}
        title={t("common.delete")}
        message={t("px.deleteConfirm")}
        confirmLabel={t("common.delete")}
        loading={remove.isPending}
      />
    </div>
  );
}

function AddProxyDialog({
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
  const [label, setLabel] = useState("");
  const [url, setUrl] = useState("");

  const create = useMutation({
    mutationFn: () => api.post("/api/proxies", { url, label: label || null }),
    onSuccess: () => {
      onClose();
      setLabel("");
      setUrl("");
      onDone();
      toast.success(t("common.success"));
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : t("common.unknownError")),
  });

  return (
    <Dialog open={open} onClose={onClose} title={t("px.add")}>
      <div className="space-y-4">
        <Field label={t("px.url")} hint={t("px.urlHint")}>
          <Input
            dir="ltr"
            className="font-mono text-xs"
            placeholder="http://user:pass@host:8080"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
          />
        </Field>
        <Field label={`${t("common.name")} (${t("common.optional")})`}>
          <Input value={label} onChange={(event) => setLabel(event.target.value)} maxLength={64} />
        </Field>
        <div className="flex justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button size="sm" loading={create.isPending} disabled={url.length < 8} onClick={() => create.mutate()}>
            {t("common.add")}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
