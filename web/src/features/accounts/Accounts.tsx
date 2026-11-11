/** X accounts — isolated workspaces with health and cookie management. */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Cookie, FlaskConical, KeyRound, Plus, ShieldAlert, UserSquare2 } from "lucide-react";
import { api, type XAccount, type Proxy } from "../../lib/api";
import { useI18n } from "../../i18n";
import { cookieErrors } from "../../i18n/ar";
import { cookieErrors as cookieErrorsEn } from "../../i18n/en";
import { useAuth } from "../auth/authContext";
import { Card, EmptyState, SectionHeader } from "../../components/ui/card";
import { Badge, Button, Field, Input, Select, Spinner, Textarea } from "../../components/ui/primitives";
import { AccountStatusBadge, HealthBar, TD, THead, TRow, TableWrap } from "../../components/ui/table";
import { ConfirmDialog, Dialog } from "../../components/ui/dialog";
import { useToast } from "../../components/ui/toast";
import { formatDateTime, formatRelative } from "../../lib/format";

export function Accounts() {
  const { t } = useI18n();
  const { hasRole } = useAuth();
  const toast = useToast();
  const queryClient = useQueryClient();
  const canManage = hasRole("operator");

  const accounts = useQuery({
    queryKey: ["accounts"],
    queryFn: () => api.get<XAccount[]>("/api/accounts"),
    refetchInterval: 10_000,
  });
  const proxies = useQuery({
    queryKey: ["proxies"],
    queryFn: () => api.get<Proxy[]>("/api/proxies"),
  });

  const [addOpen, setAddOpen] = useState(false);
  const [cookieAccount, setCookieAccount] = useState<XAccount | null>(null);
  const [deleteAccount, setDeleteAccount] = useState<XAccount | null>(null);
  const [testingId, setTestingId] = useState<number | null>(null);
  const [testResult, setTestResult] = useState<string | null>(null);

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["accounts"] });
  };

  const toggleStatus = useMutation({
    mutationFn: (account: XAccount) =>
      api.patch(`/api/accounts/${account.id}`, {
        status: account.status === "disabled" ? "active" : "disabled",
      }),
    onSuccess: invalidate,
    onError: () => toast.error(t("common.unknownError")),
  });

  const remove = useMutation({
    mutationFn: (account: XAccount) => api.delete(`/api/accounts/${account.id}`),
    onSuccess: () => {
      setDeleteAccount(null);
      invalidate();
      toast.success(t("common.success"));
    },
    onError: () => toast.error(t("common.unknownError")),
  });

  const test = async (account: XAccount) => {
    setTestingId(account.id);
    setTestResult(null);
    try {
      const result = await api.post<{ outcome: string; collected: number }>(
        `/api/accounts/${account.id}/test`,
      );
      if (result.outcome === "success") {
        toast.success(t("acc.testOk", { count: result.collected }));
      } else {
        toast.warning(t("acc.testFailed", { outcome: t(`run.outcome.${result.outcome}` as never) }));
      }
      setTestResult(`${result.outcome}:${result.collected}`);
      invalidate();
    } catch {
      toast.error(t("common.unknownError"));
    } finally {
      setTestingId(null);
    }
  };

  const rows = accounts.data ?? [];

  return (
    <div>
      <SectionHeader
        title={t("acc.title")}
        subtitle={t("acc.subtitle")}
        action={
          canManage && (
            <Button icon={<Plus className="h-4 w-4" />} onClick={() => setAddOpen(true)}>
              {t("acc.add")}
            </Button>
          )
        }
      />

      {accounts.isLoading ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : rows.length === 0 ? (
        <EmptyState
          icon={<UserSquare2 className="h-8 w-8" />}
          title={t("acc.title")}
          description={t("acc.addHint")}
        />
      ) : (
        <TableWrap>
          <THead
            columns={[
              t("common.name"),
              t("common.status"),
              t("acc.health"),
              t("acc.cookies"),
              t("acc.runs"),
              t("acc.items"),
              t("acc.proxy"),
              t("acc.lastRun"),
              canManage ? t("common.actions") : "",
            ]}
          />
          <tbody>
            {rows.map((account) => (
              <TRow key={account.id}>
                <TD>
                  <p className="font-bold text-ink-100">{account.label}</p>
                  {account.notes && <p className="text-[11px] text-ink-400">{account.notes}</p>}
                  {account.status === "cooldown" && account.cooldown_until && (
                    <p className="text-[11px] text-amber-400">
                      {t("acc.cooldownUntil", { time: formatDateTime(account.cooldown_until) })}
                    </p>
                  )}
                </TD>
                <TD>
                  <AccountStatusBadge status={account.status} />
                </TD>
                <TD>
                  <HealthBar score={account.health_score} />
                </TD>
                <TD>
                  {account.has_cookies ? (
                    <Badge tone="green">
                      <Cookie className="h-3 w-3" />
                      {t("acc.cookiesInstalled")}
                    </Badge>
                  ) : (
                    <Badge tone="amber">{t("acc.cookiesMissing")}</Badge>
                  )}
                </TD>
                <TD className="text-xs tabular-nums">
                  {account.stats.total_runs}
                  <span className="text-ink-500"> ({account.stats.successful_runs}✓)</span>
                </TD>
                <TD className="text-xs tabular-nums text-fox-300">{account.stats.items_collected}</TD>
                <TD className="text-xs text-ink-300">
                  {(() => {
                    const proxy = proxies.data?.find((item) => item.id === account.proxy_id);
                    return proxy ? proxy.label || proxy.url.replace(/^https?:\/\//, "") : t("acc.noProxy");
                  })()}
                </TD>
                <TD className="text-xs text-ink-400">{formatRelative(account.last_run_at)}</TD>
                {canManage && (
                  <TD>
                    <div className="flex items-center gap-1.5">
                      <Button
                        variant="ghost"
                        size="sm"
                        title={t("acc.cookies")}
                        onClick={() => setCookieAccount(account)}
                      >
                        <KeyRound className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        title={t("acc.test")}
                        loading={testingId === account.id}
                        onClick={() => void test(account)}
                      >
                        <FlaskConical className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        title={account.status === "disabled" ? t("acc.enable") : t("acc.disable")}
                        onClick={() => toggleStatus.mutate(account)}
                      >
                        <ShieldAlert className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        title={t("common.delete")}
                        className="text-red-400 hover:bg-red-500/10"
                        onClick={() => setDeleteAccount(account)}
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

      {testResult && (
        <Card className="mt-4 border-ink-700 bg-ink-900/40">
          <p className="text-xs text-ink-300">{testResult}</p>
        </Card>
      )}

      <AddAccountDialog
        open={addOpen}
        onClose={() => setAddOpen(false)}
        proxies={proxies.data ?? []}
        onDone={invalidate}
      />

      <CookiesDialog account={cookieAccount} onClose={() => setCookieAccount(null)} onDone={invalidate} />

      <ConfirmDialog
        open={deleteAccount !== null}
        onClose={() => setDeleteAccount(null)}
        onConfirm={() => deleteAccount && remove.mutate(deleteAccount)}
        title={t("common.delete")}
        message={t("acc.deleteConfirm")}
        confirmLabel={t("common.delete")}
        loading={remove.isPending}
      />
    </div>
  );
}

/* ------------------------------------------------------------------ */

function AddAccountDialog({
  open,
  onClose,
  proxies,
  onDone,
}: {
  open: boolean;
  onClose: () => void;
  proxies: Proxy[];
  onDone: () => void;
}) {
  const { t } = useI18n();
  const toast = useToast();

  const [label, setLabel] = useState("");
  const [notes, setNotes] = useState("");
  const [proxyId, setProxyId] = useState("");

  const create = useMutation({
    mutationFn: () =>
      api.post("/api/accounts", {
        label,
        notes: notes || null,
        proxy_id: proxyId ? Number(proxyId) : null,
      }),
    onSuccess: () => {
      onClose();
      setLabel("");
      setNotes("");
      setProxyId("");
      onDone();
      toast.success(t("common.success"));
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : t("common.unknownError")),
  });

  return (
    <Dialog open={open} onClose={onClose} title={t("acc.addTitle")}>
      <div className="space-y-4">
        <p className="rounded-lg border border-ink-700 bg-ink-900 px-3 py-2 text-xs text-ink-300">
          {t("acc.addHint")}
        </p>
        <Field label={t("acc.label")}>
          <Input value={label} onChange={(event) => setLabel(event.target.value)} maxLength={64} />
        </Field>
        <Field label={`${t("acc.notes")} (${t("common.optional")})`}>
          <Input value={notes} onChange={(event) => setNotes(event.target.value)} maxLength={500} />
        </Field>
        <Field label={`${t("acc.proxy")} (${t("common.optional")})`}>
          <Select value={proxyId} onChange={(event) => setProxyId(event.target.value)}>
            <option value="">{t("acc.noProxy")}</option>
            {proxies.map((proxy) => (
              <option key={proxy.id} value={proxy.id}>
                {proxy.label || proxy.url}
              </option>
            ))}
          </Select>
        </Field>
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="secondary" size="sm" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button
            size="sm"
            loading={create.isPending}
            disabled={label.trim().length === 0}
            onClick={() => create.mutate()}
          >
            {t("common.add")}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

/* ------------------------------------------------------------------ */

function CookiesDialog({
  account,
  onClose,
  onDone,
}: {
  account: XAccount | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t, lang } = useI18n();
  const toast = useToast();
  const [content, setContent] = useState("");

  const upload = useMutation({
    mutationFn: () =>
      api.post<{ message: string; format: string; cookie_count: number }>(
        `/api/accounts/${account!.id}/cookies`,
        { content },
      ),
    onSuccess: (result) => {
      onClose();
      setContent("");
      onDone();
      toast.success(t("acc.cookiesDone", { count: result.cookie_count }));
    },
    onError: (error) => {
      const code = error instanceof Error ? error.message : "";
      const reasons = lang === "ar" ? cookieErrors : cookieErrorsEn;
      toast.error(
        t("acc.cookiesInvalid", { reason: (reasons as Record<string, string>)[code] ?? code }),
      );
    },
  });

  const steps = [1, 2, 3, 4].map((step) => t(`acc.cookiesStep${step}` as never));

  return (
    <Dialog open={account !== null} onClose={onClose} title={t("acc.cookiesTitle")} wide>
      <div className="space-y-4">
        <ol className="space-y-2 rounded-xl border border-ink-700 bg-ink-900 p-4">
          {steps.map((step, index) => (
            <li key={index} className="flex items-start gap-2.5 text-xs leading-relaxed text-ink-300">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-fox-500/15 text-[10px] font-bold text-fox-300">
                {index + 1}
              </span>
              {step}
            </li>
          ))}
        </ol>
        <Field label="Cookie Editor JSON">
          <Textarea
            dir="ltr"
            rows={8}
            className="font-mono text-[11px]"
            placeholder={t("acc.cookiesPaste")}
            value={content}
            onChange={(event) => setContent(event.target.value)}
          />
        </Field>
        <div className="flex justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button size="sm" loading={upload.isPending} disabled={content.trim().length < 10} onClick={() => upload.mutate()}>
            {t("acc.cookiesInstall")}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
