/** Console session state — current user, login/logout, role helpers. */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { api, type UserPublic } from "../../lib/api";

export type Role = UserPublic["role"];

const ROLE_RANK: Record<Role, number> = { viewer: 1, operator: 2, admin: 3 };

interface AuthContextValue {
  user: UserPublic | null;
  ready: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  hasRole: (minimum: Role) => boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserPublic | null>(null);
  const [ready, setReady] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setUser(await api.get<UserPublic>("/api/auth/me"));
    } catch {
      setUser(null);
    } finally {
      setReady(true);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const onUnauthorized = () => setUser(null);
    window.addEventListener("xfox:unauthorized", onUnauthorized);
    return () => window.removeEventListener("xfox:unauthorized", onUnauthorized);
  }, [refresh]);

  const login = useCallback(
    async (username: string, password: string) => {
      await api.post<UserPublic>("/api/auth/login", { username, password });
      await refresh();
    },
    [refresh],
  );

  const logout = useCallback(async () => {
    try {
      await api.post("/api/auth/logout");
    } finally {
      setUser(null);
    }
  }, []);

  const hasRole = useCallback(
    (minimum: Role) => ROLE_RANK[user?.role ?? "viewer"] >= ROLE_RANK[minimum],
    [user],
  );

  const value = useMemo<AuthContextValue>(
    () => ({ user, ready, login, logout, refresh, hasRole }),
    [user, ready, login, logout, refresh, hasRole],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}
