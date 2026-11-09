import { createContext, useContext, useEffect, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";

export type Branding = { app_name: string; primary_color: string; logo_url: string | null };
const fallback: Branding = { app_name: "Customers Platform", primary_color: "#1b5e20", logo_url: null };
const Ctx = createContext<Branding>(fallback);

export function BrandingProvider({ children }: { children: ReactNode }) {
  const { data } = useQuery({ queryKey: ["branding"], queryFn: () => api.get<Branding>("/branding"), staleTime: 60_000 });
  const b = data ?? fallback;
  useEffect(() => {
    document.documentElement.style.setProperty("--brand", b.primary_color);
    document.title = b.app_name;
    const link = document.querySelector<HTMLLinkElement>("link[rel=icon]");
    if (link && b.logo_url) link.href = b.logo_url;
  }, [b]);
  return <Ctx.Provider value={b}>{children}</Ctx.Provider>;
}

export const useBranding = () => useContext(Ctx);
