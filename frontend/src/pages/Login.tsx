import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Globe, Loader2 } from "lucide-react";
import { useAuth } from "../lib/auth";
import { useBranding } from "../lib/branding";
import { Logo } from "../components/Layout";

export default function Login() {
  const { t, i18n } = useTranslation();
  const { login } = useAuth();
  const b = useBranding();
  const [u, setU] = useState("");
  const [p, setP] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setErr(null);
    try { await login(u, p); } catch (x) { setErr((x as Error).message); }
    setBusy(false);
  };

  return (
    <div className="min-h-screen grid place-items-center p-4 bg-gradient-to-br from-brand-soft to-surface">
      <div className="w-full max-w-sm">
        <div className="flex flex-col items-center mb-6 text-center">
          <Logo size={72} />
          <h1 className="text-2xl font-bold mt-4 text-brand">{b.app_name}</h1>
          <p className="text-sm text-muted">{t("login.subtitle")}</p>
        </div>
        <form onSubmit={submit} className="card p-6 space-y-4">
          <h2 className="font-semibold text-lg">{t("login.title")}</h2>
          <div>
            <label className="label">{t("login.username")}</label>
            <input className="input" autoFocus autoComplete="username" value={u} onChange={(e) => setU(e.target.value)} required />
          </div>
          <div>
            <label className="label">{t("login.password")}</label>
            <input className="input" type="password" autoComplete="current-password" value={p} onChange={(e) => setP(e.target.value)} required />
          </div>
          {err && <div className="text-sm text-bad">{err}</div>}
          <button className="btn-primary w-full justify-center py-2.5" disabled={busy}>
            {busy && <Loader2 size={16} className="animate-spin" />} {t("login.submit")}
          </button>
        </form>
        <button className="mt-4 mx-auto flex items-center gap-2 text-sm text-muted hover:text-ink cursor-pointer"
          onClick={() => i18n.changeLanguage(i18n.language === "ar" ? "en" : "ar")}>
          <Globe size={15} /> {t("app.language")}
        </button>
      </div>
    </div>
  );
}
