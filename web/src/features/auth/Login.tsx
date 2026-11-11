/** Sign-in screen. */

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Gauge } from "lucide-react";
import { ApiError } from "../../lib/api";
import { useAuth } from "./authContext";
import { useI18n } from "../../i18n";
import { Button, Field, Input } from "../../components/ui/primitives";
import { useToast } from "../../components/ui/toast";
import { fetchBootstrapStatus } from "../../App";

export function Login() {
  const { t } = useI18n();
  const { login } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    void fetchBootstrapStatus().then((initialized) => {
      if (!initialized) navigate("/setup", { replace: true });
    });
  }, [navigate]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setLoading(true);
    try {
      await login(username, password);
      navigate("/dashboard", { replace: true });
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.code === "too_many_attempts") toast.error(t("auth.tooManyAttempts"));
        else toast.error(t("auth.invalidCredentials"));
      } else {
        toast.error(t("common.unknownError"));
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-ink-950 p-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center gap-3 text-center">
          <div className="rounded-2xl bg-fox-500/15 p-4 text-fox-400">
            <Gauge className="h-10 w-10" />
          </div>
          <h1 className="text-2xl font-extrabold text-white">{t("auth.loginTitle")}</h1>
          <p className="text-xs text-ink-400">{t("auth.loginSubtitle")}</p>
        </div>

        <form
          onSubmit={submit}
          className="page-enter space-y-4 rounded-2xl border border-ink-800 bg-ink-900/70 p-6 shadow-2xl"
        >
          <Field label={t("auth.username")}>
            <Input
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              required
              autoComplete="username"
              autoFocus
            />
          </Field>
          <Field label={t("auth.password")}>
            <Input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              autoComplete="current-password"
            />
          </Field>
          <Button type="submit" loading={loading} className="w-full">
            {t("auth.login")}
          </Button>
        </form>
      </div>
    </div>
  );
}
