/** Application shell — sidebar, topbar, live risk banner. */

import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import {
  Activity,
  FolderOpen,
  Gauge,
  Globe,
  LayoutDashboard,
  ListChecks,
  LogOut,
  ScrollText,
  Settings,
  Shield,
  Users,
  UserSquare2,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api, type Overview } from "../../lib/api";
import { useAuth } from "../../features/auth/authContext";
import { useI18n } from "../../i18n";
import { Badge } from "../ui/primitives";
import { RiskBadge } from "../ui/table";

export function AppShell() {
  const { t, lang, setLang } = useI18n();
  const { user, logout, hasRole } = useAuth();
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const overview = useQuery({
    queryKey: ["overview"],
    queryFn: () => api.get<Overview>("/api/system/overview"),
    refetchInterval: 15_000,
  });

  useEffect(() => {
    setSidebarOpen(false);
  }, [location.pathname]);

  const risk = overview.data?.risk;
  const navItems = [
    { to: "/dashboard", icon: <LayoutDashboard className="h-4 w-4" />, label: t("nav.dashboard") },
    { to: "/jobs", icon: <ListChecks className="h-4 w-4" />, label: t("nav.jobs") },
    { to: "/accounts", icon: <UserSquare2 className="h-4 w-4" />, label: t("nav.accounts") },
    { to: "/proxies", icon: <Globe className="h-4 w-4" />, label: t("nav.proxies"), roles: "operator" },
    { to: "/posts", icon: <FolderOpen className="h-4 w-4" />, label: t("nav.posts") },
    { to: "/authors", icon: <Users className="h-4 w-4" />, label: t("nav.authors") },
    { to: "/events", icon: <Activity className="h-4 w-4" />, label: t("nav.events") },
    { to: "/settings", icon: <Settings className="h-4 w-4" />, label: t("nav.settings") },
    ...(hasRole("admin")
      ? [{ to: "/users", icon: <Shield className="h-4 w-4" />, label: t("nav.users") }]
      : []),
  ].filter((item) => !item.roles || hasRole(item.roles as never));

  return (
    <div className="flex min-h-screen bg-ink-950">
      {/* Sidebar */}
      <aside
        className={`fixed inset-y-0 z-40 w-60 shrink-0 border-e border-ink-800 bg-ink-900 transition-transform lg:static lg:translate-x-0 ${
          sidebarOpen ? "translate-x-0" : "translate-x-full rtl:translate-x-[-100%] lg:rtl:translate-x-0"
        } start-0 lg:start-auto`}
        style={{ insetInlineStart: 0 }}
      >
        <div className="flex h-full flex-col">
          <div className="flex items-center gap-3 border-b border-ink-800 px-5 py-5">
            <div className="rounded-xl bg-fox-500/15 p-2 text-fox-400">
              <Gauge className="h-6 w-6" />
            </div>
            <div className="min-w-0">
              <p className="truncate text-sm font-extrabold text-white">{t("nav.brand")}</p>
              <p className="truncate text-[10px] text-ink-400">{t("nav.brandSub")}</p>
            </div>
          </div>

          <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `flex items-center gap-3 rounded-lg px-3 py-2.5 text-[13px] font-semibold transition-colors ${
                    isActive
                      ? "bg-fox-500/15 text-fox-300"
                      : "text-ink-300 hover:bg-ink-800 hover:text-ink-100"
                  }`
                }
              >
                {item.icon}
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="border-t border-ink-800 p-4">
            <div className="mb-3 flex items-center justify-between">
              {risk && <RiskBadge level={risk.level} />}
              <span
                className={`inline-flex items-center gap-1.5 text-[10px] font-semibold ${
                  overview.data?.engine_running ? "text-emerald-400" : "text-red-400"
                }`}
              >
                <span
                  className={`live-dot h-1.5 w-1.5 rounded-full ${
                    overview.data?.engine_running ? "bg-emerald-400" : "bg-red-400"
                  }`}
                />
                {overview.data?.engine_running ? t("dash.engineRunning") : t("dash.enginePaused")}
              </span>
            </div>
            <div className="flex items-center justify-between gap-2">
              <div className="flex min-w-0 items-center gap-2.5">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-ink-700 text-xs font-bold text-ink-200">
                  {user?.username?.slice(0, 2).toUpperCase()}
                </div>
                <div className="min-w-0">
                  <p className="truncate text-xs font-bold text-ink-100">{user?.username}</p>
                  <p className="text-[10px] text-ink-400">{t(`role.${user?.role ?? "viewer"}` as never)}</p>
                </div>
              </div>
              <button
                onClick={() => void logout()}
                className="rounded-lg p-2 text-ink-400 transition-colors hover:bg-ink-800 hover:text-red-400"
                title={t("nav.logout")}
                aria-label={t("nav.logout")}
              >
                <LogOut className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      </aside>

      {/* Main column */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Topbar */}
        <header className="sticky top-0 z-30 flex h-14 items-center justify-between gap-4 border-b border-ink-800 bg-ink-950/90 px-4 backdrop-blur sm:px-6 lg:px-8">
          <div className="flex items-center gap-3">
            <button
              className="rounded-lg p-2 text-ink-300 hover:bg-ink-800 lg:hidden"
              onClick={() => setSidebarOpen((open) => !open)}
              aria-label="menu"
            >
              <ScrollText className="h-5 w-5" />
            </button>
            {risk?.paused && (
              <Badge tone="red" className="animate-pulse">
                {t("dash.enginePaused")}
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-2">
            {overview.data && (
              <span className="hidden items-center gap-1.5 text-[11px] text-ink-400 sm:flex">
                <FolderOpen className="h-3.5 w-3.5" />
                {overview.data.totals.posts.toLocaleString()}
              </span>
            )}
            <button
              onClick={() => setLang(lang === "ar" ? "en" : "ar")}
              className="rounded-lg border border-ink-700 px-3 py-1.5 text-[11px] font-bold text-ink-200 transition-colors hover:border-fox-500 hover:text-fox-300"
            >
              {t("misc.language")}
            </button>
          </div>
        </header>

        {/* Risk banner */}
        {risk?.paused && (
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-red-500/30 bg-red-500/10 px-6 py-2.5">
            <p className="text-xs font-semibold text-red-300">{t("dash.riskBanner.red")}</p>
          </div>
        )}
        {!risk?.paused && risk?.level === "yellow" && (
          <div className="border-b border-amber-500/30 bg-amber-500/10 px-6 py-2">
            <p className="text-xs font-semibold text-amber-300">{t("dash.riskBanner.yellow")}</p>
          </div>
        )}

        {/* Page content */}
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6 lg:px-8">
          <div key={location.pathname} className="page-enter">
            <Outlet />
          </div>
        </main>

        <footer className="mt-auto border-t border-ink-800 px-6 py-4">
          <p className="text-center text-[11px] text-ink-500">
            XFox Harvester — {t("nav.brandSub")} · Camoufox + X-CrawlFox
          </p>
        </footer>
      </div>
    </div>
  );
}
