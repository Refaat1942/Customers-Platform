import { useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import clsx from "clsx";
import {
  Activity, BarChart3, BellRing, BookOpen, Bot, Clock3, ChevronDown, DatabaseZap, Package, Search, Briefcase, FileClock, Globe, LayoutDashboard, LogOut, MapPin, Menu, PhoneCall,
  Receipt, Settings, Sparkles, Upload, UserCog, UserRound, Users, X,
} from "lucide-react";
import { useAuth } from "../lib/auth";
import { useBranding } from "../lib/branding";
import { api } from "../lib/api";
import { Notice } from "./ui";

type Item = { to: string; key: string; perm: string | null; icon: typeof Users };
type Group = { key: string; items: Item[] };

/** Grouped by what you want to do - each group can be folded away. */
const GROUPS_NAV: Group[] = [
  { key: "today", items: [
    { to: "/", key: "dashboard", perm: "dashboard", icon: LayoutDashboard },
    { to: "/live", key: "live", perm: "live", icon: Activity },
  ] },
  { key: "customers", items: [
    { to: "/customers", key: "customers", perm: "customers", icon: Users },
  ] },
  { key: "act", items: [
    { to: "/recommendations", key: "recommendations", perm: "recommendations", icon: PhoneCall },
    { to: "/refills", key: "refills", perm: "refills", icon: BellRing },
  ] },
  { key: "analysis", items: [
    { to: "/insights", key: "insights", perm: "insights", icon: Sparkles },
    { to: "/business", key: "business", perm: "business", icon: Briefcase },
    { to: "/products", key: "products", perm: "products", icon: Package },
    { to: "/shifts", key: "shifts", perm: "shifts", icon: Clock3 },
    { to: "/area", key: "area", perm: "area", icon: MapPin },
    { to: "/transactions", key: "transactions", perm: "transactions", icon: Receipt },
    { to: "/ai", key: "ai", perm: "ai", icon: Bot },
  ] },
  { key: "data", items: [
    { to: "/import", key: "import", perm: "import", icon: Upload },
    { to: "/data-check", key: "datacheck", perm: "data_check", icon: DatabaseZap },
  ] },
  { key: "admin", items: [
    { to: "/users", key: "users", perm: "users", icon: UserCog },
    { to: "/settings", key: "settings", perm: "settings", icon: Settings },
    { to: "/audit", key: "audit", perm: "audit", icon: FileClock },
  ] },
  { key: "help", items: [
    { to: "/glossary", key: "glossary", perm: null, icon: BookOpen },
  ] },
];

export function Logo({ size = 36 }: { size?: number }) {
  const b = useBranding();
  return b.logo_url ? (
    <img src={b.logo_url} alt="" style={{ height: size, width: size }} className="object-contain rounded-md logo-side" />
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

  const nav_ = useNavigate();
  const [find, setFind] = useState("");
  const [closed, setClosed] = useState<string[]>(() => {
    try { return JSON.parse(localStorage.getItem("cp_nav_closed") || "[]"); } catch { return []; }
  });
  const toggleGroup = (k: string) => setClosed((c) => {
    const n = c.includes(k) ? c.filter((x) => x !== k) : [...c, k];
    try { localStorage.setItem("cp_nav_closed", JSON.stringify(n)); } catch { /* */ }
    return n;
  });
  const allowed = (i: Item) => !i.perm || can(i.perm) || (i.perm === "customers" && can("customer_base"));
  const visible = GROUPS_NAV.map((g) => ({ ...g, items: g.items.filter(allowed) }))
    .filter((g) => g.items.length);
  const q = find.trim().toLowerCase();
  const matches = (i: Item) => !q || `${t(`nav.${i.key}`)} ${t(`navHint.${i.key}`)}`.toLowerCase().includes(q);
  const isActive = (to: string) => (to === "/" ? loc.pathname === "/" : loc.pathname.startsWith(to));

  const goFind = (e: React.FormEvent) => {
    e.preventDefault();
    const hit = visible.flatMap((g) => g.items).find(matches);
    const looksLikeCustomer = /\d{4,}/.test(find) || (!hit && find.trim().length >= 2);
    if (looksLikeCustomer && can("customers")) nav_(`/customers?q=${encodeURIComponent(find.trim())}`);
    else if (hit) nav_(hit.to);
    setFind(""); setOpen(false);
  };

  const link = (i: Item) => (
    <NavLink key={i.to} to={i.to} end={i.to === "/"} onClick={() => { setOpen(false); setFind(""); }} title={t(`navHint.${i.key}`)}
      className={({ isActive: a }) => clsx("flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition",
        a ? "bg-brand text-white" : "text-ink/80 hover:bg-brand-soft")}>
      <i.icon size={17} className="shrink-0" />
      <span className="flex-1 min-w-0">
        <span className="block truncate">{t(`nav.${i.key}`)}</span>
        {q && <span className="block text-[11px] opacity-70 truncate">{t(`navHint.${i.key}`)}</span>}
      </span>
    </NavLink>
  );

  return (
    <div className="min-h-screen flex">
      {open && <div className="fixed inset-0 bg-black/30 z-30 lg:hidden" onClick={() => setOpen(false)} />}
      <aside className={clsx("fixed lg:sticky top-0 z-40 h-screen w-64 shrink-0 bg-white border-e border-line flex flex-col transition-transform",
        open ? "translate-x-0" : "ltr:-translate-x-full rtl:translate-x-full lg:!translate-x-0")}>
        <Link to="/" className="flex items-center gap-3 px-4 py-4 border-b border-line">
          <span className="shrink-0 rounded-2xl bg-white border border-line shadow-sm p-1.5 grid place-items-center"><Logo size={54} /></span>
          <div className="leading-tight min-w-0">
            <div className="font-bold text-[15px] leading-tight line-clamp-2">{b.app_name}</div>
            <div className="text-xs text-muted">{t("login.subtitle")}</div>
          </div>
        </Link>
        <form onSubmit={goFind} className="px-3 pt-3">
          <div className="relative">
            <Search size={15} className="absolute top-2.5 start-3 text-muted" />
            <input className="input ps-9 py-2 text-sm" placeholder={t("nav.find")} value={find} onChange={(e) => setFind(e.target.value)} />
          </div>
        </form>
        <nav className="flex-1 overflow-auto p-3 space-y-1">
          {visible.map((g) => {
            const items = g.items.filter(matches);
            if (!items.length) return null;
            const folded = !q && closed.includes(g.key) && !g.items.some((i) => isActive(i.to));
            return (
              <div key={g.key} className="pb-1">
                <button type="button" onClick={() => toggleGroup(g.key)}
                  className="w-full flex items-center gap-2 px-3 pt-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-muted hover:text-ink cursor-pointer">
                  <span className="flex-1 text-start">{t(`navGroup.${g.key}`)}</span>
                  <ChevronDown size={13} className={clsx("transition", folded && "-rotate-90 rtl:rotate-90")} />
                </button>
                {!folded && <div className="space-y-0.5">{items.map(link)}</div>}
              </div>
            );
          })}
          {q && /\d{4,}|\D{2,}/.test(find) && can("customers") && (
            <button onClick={goFind} className="w-full text-start rounded-lg px-3 py-2 text-sm text-brand hover:bg-brand-soft cursor-pointer">
              {t("nav.findCustomer", { q: find.trim() })}
            </button>
          )}
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
