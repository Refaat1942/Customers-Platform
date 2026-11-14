import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import i18n from "../i18n";
import { api, getToken, setToken, setUnauthorizedHandler } from "./api";

export type User = {
  id: number; username: string; full_name: string | null; role: string; branches: string[];
  language: "en" | "ar"; permissions: string[]; default_password?: boolean;
};

type Ctx = {
  user: User | null; ready: boolean;
  login: (u: string, p: string) => Promise<void>; logout: () => void; can: (p: string) => boolean;
  refresh: () => Promise<void>;
};

const AuthCtx = createContext<Ctx>(null!);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const qc = useQueryClient();

  // forget all data on sign-out, but keep the branding (logo, name, colour) for the login page
  const logout = useCallback(() => {
    setToken(null); setUser(null);
    qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "branding" });
  }, [qc]);

  const refresh = useCallback(async () => {
    if (!getToken()) { setReady(true); return; }
    try { setUser(await api.get<User>("/auth/me")); } catch { setToken(null); setUser(null); }
    setReady(true);
  }, []);

  useEffect(() => { setUnauthorizedHandler(logout); refresh(); }, [logout, refresh]);

  const login = async (username: string, password: string) => {
    const r = await api.post<{ token: string; user: User }>("/auth/login", { username, password });
    setToken(r.token);
    if (r.user.language && r.user.language !== i18n.language) i18n.changeLanguage(r.user.language);
    await refresh();
  };

  const can = (p: string) => !!user?.permissions.includes(p);
  return <AuthCtx.Provider value={{ user, ready, login, logout, can, refresh }}>{children}</AuthCtx.Provider>;
}

export const useAuth = () => useContext(AuthCtx);
