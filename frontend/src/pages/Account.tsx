import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Card, Notice, PageHeader } from "../components/ui";

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
      <Card title={t("account.changePassword")} className="max-w-md">
        <form onSubmit={save} className="space-y-4">
          <div><label className="label">{t("account.current")}</label><input className="input" type="password" autoComplete="current-password" required value={cur} onChange={(e) => setCur(e.target.value)} /></div>
          <div><label className="label">{t("account.newPw")}</label><input className="input" type="password" autoComplete="new-password" minLength={8} required value={pw} onChange={(e) => setPw(e.target.value)} /></div>
          {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
          <button className="btn-primary">{t("app.save")}</button>
        </form>
      </Card>
    </>
  );
}
