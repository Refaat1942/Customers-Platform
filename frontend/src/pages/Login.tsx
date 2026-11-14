import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { BarChart3, BellRing, Eye, EyeOff, Globe, Loader2, Lock, ShieldCheck, Sparkles, User, Users } from "lucide-react";
import { useAuth } from "../lib/auth";
import { useBranding } from "../lib/branding";

const REMEMBER_KEY = "cp_last_username";

function BrandLogo({ size }: { size: number }) {
  const b = useBranding();
  const [broken, setBroken] = useState(false);
  useEffect(() => setBroken(false), [b.logo_url]);
  if (b.logo_url && !broken) {
    return <img src={b.logo_url} alt={b.app_name} onError={() => setBroken(true)}
      style={{ maxHeight: size, maxWidth: size * 2.2 }} className="object-contain" />;
  }
  return <div style={{ height: size, width: size }} className="rounded-2xl bg-white/15 text-white grid place-items-center"><BarChart3 size={size * 0.55} /></div>;
}

export default function Login() {
  const { t, i18n } = useTranslation();
  const { login } = useAuth();
  const b = useBranding();
  const saved = (() => { try { return localStorage.getItem(REMEMBER_KEY) || ""; } catch { return ""; } })();
  const [u, setU] = useState(saved);
  const [p, setP] = useState("");
  const [show, setShow] = useState(false);
  const [remember, setRemember] = useState(!!saved);
  const [caps, setCaps] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const ar = i18n.language === "ar";

  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setErr(null);
    try {
      await login(u.trim(), p);
      try { remember ? localStorage.setItem(REMEMBER_KEY, u.trim()) : localStorage.removeItem(REMEMBER_KEY); } catch { /* */ }
    } catch (x) { setErr((x as Error).message); }
    setBusy(false);
  };
  const capsCheck = (e: React.KeyboardEvent) => setCaps(e.getModifierState?.("CapsLock") ?? false);

  const features = [
    { icon: Users, text: t("login.f1") },
    { icon: BellRing, text: t("login.f2") },
    { icon: Sparkles, text: t("login.f3") },
  ];

  return (
    <div className="min-h-screen grid lg:grid-cols-[1.1fr_1fr] bg-surface">
      {/* brand panel */}
      <div className="relative hidden lg:flex flex-col justify-between p-12 text-white overflow-hidden"
        style={{ background: "linear-gradient(140deg, var(--brand, #1b5e20) 0%, color-mix(in srgb, var(--brand, #1b5e20) 65%, black) 100%)" }}>
        <div className="absolute -top-24 -end-24 size-96 rounded-full bg-white/5" />
        <div className="absolute -bottom-32 -start-20 size-[28rem] rounded-full bg-white/5" />
        <div className="relative flex items-center gap-4">
          <div className="rounded-2xl bg-white p-3 shadow-lg"><BrandLogo size={56} /></div>
          <div>
            <div className="text-2xl font-bold">{b.app_name}</div>
            <div className="text-white/75 text-sm">{t("login.subtitle")}</div>
          </div>
        </div>
        <div className="relative max-w-md">
          <h2 className="text-3xl font-bold leading-tight">{t("login.headline")}</h2>
          <p className="text-white/75 mt-3">{t("login.tagline")}</p>
          <ul className="mt-8 space-y-4">
            {features.map((f) => (
              <li key={f.text} className="flex items-center gap-3">
                <span className="size-9 rounded-xl bg-white/15 grid place-items-center shrink-0"><f.icon size={18} /></span>
                <span className="text-white/90">{f.text}</span>
              </li>
            ))}
          </ul>
        </div>
        <div className="relative text-xs text-white/60 flex items-center gap-2"><ShieldCheck size={14} /> {t("login.secure")}</div>
      </div>

      {/* form */}
      <div className="flex flex-col items-center justify-center p-6">
        <div className="w-full max-w-sm">
          <div className="lg:hidden flex flex-col items-center text-center mb-8">
            <div className="rounded-2xl bg-white p-3 shadow-sm border border-line" style={{ background: "white" }}>
              <div style={{ filter: "none" }}><BrandLogoLight size={64} /></div>
            </div>
            <h1 className="text-2xl font-bold mt-4 text-brand">{b.app_name}</h1>
            <p className="text-sm text-muted">{t("login.subtitle")}</p>
          </div>

          <h2 className="text-2xl font-bold">{t("login.welcome")}</h2>
          <p className="text-sm text-muted mt-1 mb-6">{t("login.hint")}</p>

          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="label" htmlFor="username">{t("login.username")}</label>
              <div className="relative">
                <User size={17} className="absolute top-1/2 -translate-y-1/2 start-3 text-muted" />
                <input id="username" className="input ps-10 py-2.5" autoFocus={!saved} autoComplete="username" autoCapitalize="none"
                  autoCorrect="off" spellCheck={false} value={u} onChange={(e) => setU(e.target.value)} onKeyUp={capsCheck} required />
              </div>
              <p className="text-[11px] text-muted mt-1">{t("login.caseSensitive")}</p>
            </div>
            <div>
              <label className="label" htmlFor="password">{t("login.password")}</label>
              <div className="relative">
                <Lock size={17} className="absolute top-1/2 -translate-y-1/2 start-3 text-muted" />
                <input id="password" className="input ps-10 pe-11 py-2.5" type={show ? "text" : "password"} autoFocus={!!saved}
                  autoComplete="current-password" value={p} onChange={(e) => setP(e.target.value)} onKeyUp={capsCheck} onKeyDown={capsCheck} required />
                <button type="button" onClick={() => setShow(!show)} aria-label={show ? t("login.hide") : t("login.show")} title={show ? t("login.hide") : t("login.show")}
                  className="absolute top-1/2 -translate-y-1/2 end-2 p-1.5 rounded-md text-muted hover:text-ink hover:bg-surface cursor-pointer">
                  {show ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
              {caps && <p className="text-xs text-warn mt-1 font-medium">⇪ {t("login.caps")}</p>}
            </div>
            <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
              <input type="checkbox" className="accent-brand size-4" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
              {t("login.remember")}
            </label>
            {err && <div className="rounded-lg border border-red-200 bg-red-50 text-bad text-sm px-3 py-2">{err}</div>}
            <button type="submit" className="btn-primary w-full justify-center py-3 text-base" disabled={busy}>
              {busy && <Loader2 size={18} className="animate-spin" />} {t("login.submit")}
            </button>
          </form>

          <div className="flex items-center justify-between mt-8 text-sm text-muted">
            <button className="flex items-center gap-2 hover:text-ink cursor-pointer" onClick={() => i18n.changeLanguage(ar ? "en" : "ar")}>
              <Globe size={15} /> {t("app.language")}
            </button>
            <span className="text-xs">© {new Date().getFullYear()} {b.app_name}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

/** Logo on a light background (mobile header): the default icon uses the brand colour. */
function BrandLogoLight({ size }: { size: number }) {
  const b = useBranding();
  const [broken, setBroken] = useState(false);
  if (b.logo_url && !broken) {
    return <img src={b.logo_url} alt={b.app_name} onError={() => setBroken(true)} style={{ maxHeight: size, maxWidth: size * 2.2 }} className="object-contain" />;
  }
  return <div style={{ height: size, width: size }} className="rounded-2xl bg-brand text-white grid place-items-center"><BarChart3 size={size * 0.55} /></div>;
}
