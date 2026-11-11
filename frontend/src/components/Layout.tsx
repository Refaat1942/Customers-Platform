import { useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import clsx from "clsx";
import {
  Activity, BarChart3, BookUser, Bot, Package, Briefcase, FileClock, Globe, LayoutDashboard, LogOut, MapPin, Menu, PhoneCall,
  Receipt, Settings, Sparkles, Upload, UserCog, UserRound, Users, X,
} from "lucide-react";
import { useAuth } from "../lib/auth";
import { useBranding } from "../lib/branding";
import { api } from "../lib/api";
import { Notice } from "./ui";

type Item = { to: string; key: string; perm: string; icon: typeof Users };

const ANALYSIS: Item[] = [
  { to: "/", key: "dashboard", perm: "dashboard", icon: LayoutDashboard },
  { to: "/live", key: "live", perm: "dashboard", icon: Activity },
  { to: "/insights", key: "insights", perm: "insights", icon: Sparkles },
  { to: "/customers", key: "customers", perm: "customers", icon: Users },
  { to: "/customer-base", key: "base", perm: "customers", icon: BookUser },
  { to: "/recommendations", key: "recommendations", perm: "recommendations", icon: PhoneCall },
  { to: "/business", key: "business", perm: "business", icon: Briefcase },
  { to: "/products", key: "products", perm: "business", icon: Package },
  { to: "/area", key: "area", perm: "area", icon: MapPin },
  { to: "/transactions", key: "transactions", perm: "transactions", icon: Receipt },
  { to: "/ai", key: "ai", perm: "ai", icon: Bot },
];
const ADMIN: Item[] = [
  { to: "/import", key: "import", perm: "import", icon: Upload },
  { to: "/users", key: "users", perm: "users", icon: UserCog },
  { to: "/settings", key: "settings", perm: "settings", icon: Settings },
  { to: "/audit", key: "audit", perm: "audit", icon: FileClock },
];

export function Logo({ size = 36 }: { size?: number }) {
  const b = useBranding();
  return b.logo_url ? (
    <img src={b.logo_url} alt="" style={{ height: size, width: size }} className="object-contain rounded-md" />
  ) : (
    <div style={{ height: size, width: size }} className="rounded-lg bg-brand text-white grid place-items-center"><BarChart3 size={size * 0.55} /></div>
  );
}

export default function Layout() {
  const { t, i18n } = useTranslation();
  const { user, logout, can } = useAuth();
  const b = useBranding();
  const [open, setOpen] = useState(false);
  const loc = useLocation();

  const toggleLang = () => {
    const l = i18n.language === "ar" ? "en" : "ar";
    i18n.changeLanguage(l);
    api.put("/auth/me", { language: l }).catch(() => {});
  };

  const nav = (items: Item[]) => items.filter((i) => can(i.perm)).map((i) => (
    <NavLink key={i.to} to={i.to} end={i.to === "/"} onClick={() => setOpen(false)}
      className={({ isActive }) => clsx("flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition",
        isActive ? "bg-brand text-white" : "text-ink/80 hover:bg-brand-soft")}>
      <i.icon size={17} /> {t(`nav.${i.key}`)}
    </NavLink>
  ));
  const adminItems = nav(ADMIN);

  return (
    <div className="min-h-screen flex">
      {open && <div className="fixed inset-0 bg-black/30 z-30 lg:hidden" onClick={() => setOpen(false)} />}
      <aside className={clsx("fixed lg:sticky top-0 z-40 h-screen w-64 shrink-0 bg-white border-e border-line flex flex-col transition-transform",
        open ? "translate-x-0" : "ltr:-translate-x-full rtl:translate-x-full lg:!translate-x-0")}>
        <Link to="/" className="flex items-center gap-3 px-5 py-5 border-b border-line">
          <Logo />
          <div className="leading-tight min-w-0">
            <div className="font-bold truncate">{b.app_name}</div>
            <div className="text-xs text-muted">{t("login.subtitle")}</div>
          </div>
        </Link>
        <nav className="flex-1 overflow-auto p-3 space-y-1">
          <div className="px-3 pt-2 pb-1 text-[11px] font-semibold uppercase tracking-wider text-muted">{t("nav.analysis")}</div>
          {nav(ANALYSIS)}
          {adminItems.length > 0 && <div className="px-3 pt-5 pb-1 text-[11px] font-semibold uppercase tracking-wider text-muted">{t("nav.admin")}</div>}
          {adminItems}
        </nav>
        <div className="p-3 border-t border-line space-y-1">
          <NavLink to="/account" onClick={() => setOpen(false)} className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm hover:bg-brand-soft">
            <UserRound size={17} />
            <span className="truncate flex-1">{user?.full_name || user?.username}</span>
            <span className="text-[10px] uppercase text-muted">{user?.role}</span>
          </NavLink>
          <button onClick={toggleLang} className="w-full flex items-center gap-3 rounded-lg px-3 py-2 text-sm hover:bg-brand-soft cursor-pointer">
            <Globe size={17} /> {t("app.language")}
          </button>
          <button onClick={logout} className="w-full flex items-center gap-3 rounded-lg px-3 py-2 text-sm text-bad hover:bg-red-50 cursor-pointer">
            <LogOut size={17} /> {t("app.signOut")}
          </button>
        </div>
      </aside>

      <div className="flex-1 min-w-0">
        <header className="lg:hidden sticky top-0 z-20 bg-white border-b border-line flex items-center gap-3 px-4 py-3">
          <button onClick={() => setOpen(!open)} className="cursor-pointer">{open ? <X /> : <Menu />}</button>
          <Logo size={28} /><span className="font-semibold truncate">{b.app_name}</span>
        </header>
        <main className="p-4 md:p-7 max-w-[1600px] mx-auto">
          {user?.default_password && loc.pathname !== "/account" && (
            <div className="mb-5"><Notice kind="danger">{t("app.defaultPassword")} <Link to="/account" className="underline font-semibold">{t("app.changeNow")}</Link></Notice></div>
          )}
          <Outlet />
        </main>
      </div>
    </div>
  );
}
