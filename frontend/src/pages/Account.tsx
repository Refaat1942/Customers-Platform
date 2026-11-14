import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Loader2, LogOut, ShieldCheck } from "lucide-react";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useBranding } from "../lib/branding";
import { Badge, Card, Notice, PageHeader } from "../components/ui";

export default function Account() {
  const { t } = useTranslation();
  const { user, refresh } = useAuth();
  const [cur, setCur] = useState("");
  const [pw, setPw] = useState("");
  const [msg, setMsg] = useState<{ kind: "success" | "danger"; text: string } | null>(null);
  const save = async (e: React.FormEvent) => {
    e.preventDefault(); setMsg(null);
    try { await api.put("/auth/me", { current_password: cur, new_password: pw }); setCur(""); setPw(""); setMsg({ kind: "success", text: t("account.changed") }); refresh(); }
    catch (x) { setMsg({ kind: "danger", text: (x as Error).message }); }
  };
  return (
    <>
      <PageHeader title={t("account.title")} subtitle={`${user?.username} · ${user?.role}${user?.branches.length ? " · " + user.branches.join(", ") : ""}`} />
      <div className="grid xl:grid-cols-2 gap-5 items-start">
        <Card title={t("account.changePassword")}>
          <form onSubmit={save} className="space-y-4 max-w-md">
            <div><label className="label">{t("account.current")}</label><input className="input" type="password" autoComplete="current-password" required value={cur} onChange={(e) => setCur(e.target.value)} /></div>
            <div><label className="label">{t("account.newPw")}</label><input className="input" type="password" autoComplete="new-password" minLength={8} required value={pw} onChange={(e) => setPw(e.target.value)} /></div>
            {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
            <button className="btn-primary">{t("app.save")}</button>
          </form>
        </Card>
        <TwoFactorCard />
      </div>
    </>
  );
}

export function TwoFactorCard() {
  const { t } = useTranslation();
  const { user, refresh } = useAuth();
  const [setup, setSetup] = useState<{ secret: string; qr_svg: string } | null>(null);
  const [code, setCode] = useState("");
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: "success" | "danger"; text: string } | null>(null);
  const on = !!user?.two_factor;

  const start = async () => {
    setMsg(null); setBusy(true);
    try { setSetup(await api.post("/auth/2fa/setup")); } catch (e) { setMsg({ kind: "danger", text: (e as Error).message }); }
    setBusy(false);
  };
  const enable = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setMsg(null);
    try { await api.post("/auth/2fa/enable", { code }); setSetup(null); setCode(""); setMsg({ kind: "success", text: t("tfa.enabled") }); await refresh(); }
    catch (x) { setMsg({ kind: "danger", text: (x as Error).message }); }
    setBusy(false);
  };
  const disable = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setMsg(null);
    try { await api.post("/auth/2fa/disable", { code, password: pw }); setCode(""); setPw(""); await refresh(); }
    catch (x) { setMsg({ kind: "danger", text: (x as Error).message }); }
    setBusy(false);
  };

  return (
    <Card title={<span className="inline-flex items-center gap-2"><ShieldCheck size={18} className="text-brand" /> {t("tfa.title")} <Badge kind={on ? "active" : "unknown"}>{on ? t("tfa.on") : t("tfa.off")}</Badge></span>}>
      <p className="text-sm text-muted mb-4">{t("tfa.intro")}</p>
      {msg && <div className="mb-4"><Notice kind={msg.kind}>{msg.text}</Notice></div>}
      {on ? (
        <form onSubmit={disable} className="space-y-3 max-w-md">
          <p className="text-sm">{t("tfa.disableHelp")}</p>
          <input className="input" type="password" placeholder={t("account.current")} value={pw} onChange={(e) => setPw(e.target.value)} required />
          <input className="input font-mono tracking-widest" inputMode="numeric" placeholder={t("tfa.code")} value={code} onChange={(e) => setCode(e.target.value)} required />
          <button className="btn-danger" disabled={busy}>{t("tfa.disable")}</button>
        </form>
      ) : !setup ? (
        <button className="btn-primary" onClick={start} disabled={busy}>{busy && <Loader2 size={16} className="animate-spin" />} {t("tfa.start")}</button>
      ) : (
        <form onSubmit={enable} className="space-y-4">
          <p className="text-sm">{t("tfa.step1")}</p>
          <p className="text-sm">{t("tfa.step2")}</p>
          <div className="inline-block bg-white border border-line rounded-xl p-2" dir="ltr" dangerouslySetInnerHTML={{ __html: setup.qr_svg }} />
          <p className="text-xs text-muted">{t("tfa.manual")} <code className="bg-surface px-2 py-0.5 rounded font-mono select-all" dir="ltr">{setup.secret.match(/.{1,4}/g)?.join(" ")}</code></p>
          <p className="text-sm">{t("tfa.step3")}</p>
          <div className="flex gap-2 max-w-sm">
            <input autoFocus className="input text-center text-xl tracking-[0.35em] font-mono" inputMode="numeric" maxLength={7} placeholder="123 456"
              value={code} onChange={(e) => setCode(e.target.value.replace(/[^\d ]/g, ""))} />
            <button className="btn-primary whitespace-nowrap" disabled={busy || code.replace(/\D/g, "").length !== 6}>{t("tfa.confirm")}</button>
          </div>
        </form>
      )}
    </Card>
  );
}

/** Shown instead of the program when the organisation requires 2-step sign-in and it isn't set up yet. */
export function ForcedTwoFactor() {
  const { t } = useTranslation();
  const { logout } = useAuth();
  const b = useBranding();
  return (
    <div className="min-h-screen bg-surface grid place-items-center p-4">
      <div className="w-full max-w-xl space-y-4">
        <div className="text-center">
          <div className="text-xl font-bold text-brand">{b.app_name}</div>
          <Notice kind="warning">{t("tfa.required")}</Notice>
        </div>
        <TwoFactorCard />
        <button className="btn-ghost mx-auto flex" onClick={logout}><LogOut size={15} /> {t("app.signOut")}</button>
      </div>
    </div>
  );
}
