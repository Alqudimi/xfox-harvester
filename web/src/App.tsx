import { Navigate, Route, Routes } from "react-router-dom";
import { api } from "./lib/api";
import { useAuth } from "./features/auth/authContext";
import { AppShell } from "./components/layout/AppShell";
import { Setup } from "./features/auth/Setup";
import { Login } from "./features/auth/Login";
import { Dashboard } from "./features/dashboard/Dashboard";
import { Jobs } from "./features/jobs/Jobs";
import { JobDetail } from "./features/jobs/JobDetail";
import { Accounts } from "./features/accounts/Accounts";
import { Proxies } from "./features/proxies/Proxies";
import { Posts } from "./features/posts/Posts";
import { Authors } from "./features/posts/Authors";
import { Events } from "./features/events/Events";
import { Settings } from "./features/settings/Settings";
import { Users } from "./features/users/Users";
import { Spinner } from "./components/ui/primitives";

function FullPageSpinner() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-ink-950">
      <div className="flex flex-col items-center gap-3">
        <div className="rounded-2xl bg-fox-500/15 p-4 text-fox-400">
          <Spinner className="h-8 w-8" />
        </div>
        <p className="text-xs font-semibold text-ink-400">XFox Harvester…</p>
      </div>
    </div>
  );
}

export function App() {
  const { user, ready } = useAuth();

  if (!ready) return <FullPageSpinner />;

  if (!user) {
    return (
      <Routes>
        <Route path="/setup" element={<Setup />} />
        <Route path="*" element={<Login />} />
      </Routes>
    );
  }

  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/jobs" element={<Jobs />} />
        <Route path="/jobs/:id" element={<JobDetail />} />
        <Route path="/accounts" element={<Accounts />} />
        <Route path="/proxies" element={<Proxies />} />
        <Route path="/posts" element={<Posts />} />
        <Route path="/authors" element={<Authors />} />
        <Route path="/events" element={<Events />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/users" element={<Users />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Route>
    </Routes>
  );
}

/** Helper reused by Login/Setup to decide the entry screen. */
export async function fetchBootstrapStatus(): Promise<boolean> {
  const status = await api.get<{ initialized: boolean }>("/api/auth/bootstrap-status");
  return status.initialized;
}
