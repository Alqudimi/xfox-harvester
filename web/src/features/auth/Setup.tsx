/** First-run admin bootstrap screen. */

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Gauge, ShieldCheck } from "lucide-react";
import { api, ApiError } from "../../lib/api";
import { useAuth } from "./authContext";
import { useI18n } from "../../i18n";
import { Button, Field, Input } from "../../components/ui/primitives";
import { useToast } from "../../components/ui/toast";
import { fetchBootstrapStatus } from "../../App";

export function Setup() {
  const { t } = useI18n();
  const { refresh } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();

  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    void fetchBootstrapStatus().then((initialized) => {
      if (initialized) navigate("/login", { replace: true });
    });
  }, [navigate]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (password !== confirm) {
      toast.error(t("auth.passwordMismatch"));
      return;
    }
    if (password.length < 8) {
      toast.error(t("auth.passwordTooShort"));
      return;
    }
    setLoading(true);
    try {
      await api.post("/api/auth/setup", {
        username,
        password,
        display_name: displayName || null,
      });
      await refresh();
      toast.success(t("common.success"));
      navigate("/dashboard", { replace: true });
    } catch (error) {
      toast.error(error instanceof ApiError ? error.code : t("common.unknownError"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-ink-950 p-4">
      <div className="w-full max-w-md">
        <div className="mb-6 flex flex-col items-center gap-3 text-center">
          <div className="rounded-2xl bg-fox-500/15 p-4 text-fox-400">
            <Gauge className="h-10 w-10" />
          </div>
          <h1 className="text-2xl font-extrabold text-white">{t("nav.brand")}</h1>
          <p className="text-xs text-ink-400">{t("nav.brandSub")}</p>
        </div>

        <form
          onSubmit={submit}
          className="page-enter space-y-4 rounded-2xl border border-ink-800 bg-ink-900/70 p-6 shadow-2xl"
        >
          <div className="flex items-center gap-2 rounded-lg border border-fox-500/30 bg-fox-500/10 px-3 py-2.5">
            <ShieldCheck className="h-4 w-4 shrink-0 text-fox-400" />
            <p className="text-xs leading-relaxed text-fox-200">{t("auth.setupSubtitle")}</p>
          </div>

          <Field label={t("auth.username")}>
            <Input
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              required
              minLength={3}
              maxLength={32}
              autoComplete="username"
            />
          </Field>
          <Field label={`${t("auth.displayName")} (${t("common.optional")})`}>
            <Input value={displayName} onChange={(event) => setDisplayName(event.target.value)} maxLength={64} />
          </Field>
          <Field label={t("auth.password")}>
            <Input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              minLength={8}
              autoComplete="new-password"
            />
          </Field>
          <Field label={t("auth.confirmPassword")}>
            <Input
              type="password"
              value={confirm}
              onChange={(event) => setConfirm(event.target.value)}
              required
              minLength={8}
              autoComplete="new-password"
            />
          </Field>

          <Button type="submit" loading={loading} className="w-full">
            {t("auth.createAdmin")}
          </Button>
        </form>
      </div>
    </div>
  );
}
