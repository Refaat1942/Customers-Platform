import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Copy, ImageUp, KeyRound, Trash2 } from "lucide-react";
import { api } from "../lib/api";
import { useBranding } from "../lib/branding";
import { Logo } from "../components/Layout";
import { Badge, Card, Notice, PageHeader, Spinner } from "../components/ui";
import DataTable from "../components/DataTable";
import { fmtDate, fmtInt, fmtMoney } from "../lib/format";

type S = { active_days: number; attention_days: number; high_value_spend: number; loyalty_spend: number; loyalty_visits: number; openai_model: string; openai_key_set: boolean; openai_key_hint: string };

export default function Settings() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["settings"], queryFn: () => api.get<S>("/settings") });
  const [s, setS] = useState<S | null>(null);
  const [key, setKey] = useState("");
  const [msg, setMsg] = useState<{ kind: "success" | "danger"; text: string; at: string } | null>(null);
  useEffect(() => { if (q.data) setS(q.data); }, [q.data]);

  const save = async (at: string, extra: Record<string, unknown> = {}) => {
    if (!s) return;
    setMsg(null);
    try {
      const body = { active_days: s.active_days, attention_days: s.attention_days, high_value_spend: s.high_value_spend, loyalty_spend: s.loyalty_spend, loyalty_visits: s.loyalty_visits, openai_model: s.openai_model, ...extra };
      setS(await api.put<S>("/settings", body)); setKey("");
      setMsg({ kind: "success", text: t("app.saved"), at });
      qc.invalidateQueries();
    } catch (e) { setMsg({ kind: "danger", text: (e as Error).message, at }); }
  };
  const num = (k: keyof S) => ({
    type: "number", className: "input", value: String(s?.[k] ?? ""),
    onChange: (e: React.ChangeEvent<HTMLInputElement>) => setS({ ...s!, [k]: Number(e.target.value) }),
  });
  const note = (at: string) => msg?.at === at && <div className="mt-3"><Notice kind={msg.kind}>{msg.text}</Notice></div>;

  if (!s) return <Spinner />;
  return (
    <>
      <PageHeader title={t("settings.title")} />
      <div className="grid xl:grid-cols-2 gap-5">
        <Card title={t("settings.rules")}>
          <div className="grid sm:grid-cols-2 gap-4">
            <div><label className="label">{t("settings.activeDays")}</label><input {...num("active_days")} min={1} /></div>
            <div><label className="label">{t("settings.attentionDays")}</label><input {...num("attention_days")} min={1} /></div>
            <div><label className="label">{t("settings.highValue")}</label><input {...num("high_value_spend")} min={0} /></div>
            <div><label className="label">{t("settings.loyaltySpend")}</label><input {...num("loyalty_spend")} min={0} /></div>
            <div><label className="label">{t("settings.loyaltyVisits")}</label><input {...num("loyalty_visits")} min={1} /></div>
          </div>
          <button className="btn-primary mt-4" onClick={() => save("rules")}>{t("app.save")}</button>
          {note("rules")}
        </Card>

        <Card title={t("settings.ai")}>
          <div className="space-y-4">
            <div className="text-sm">{s.openai_key_set ? <span className="text-good font-semibold">✓ {t("settings.keySet")} ({s.openai_key_hint})</span> : <span className="text-muted">{t("settings.keyNotSet")}</span>}</div>
            <div><label className="label">{t("settings.apiKey")}</label>
              <input className="input font-mono" type="password" autoComplete="off" placeholder="sk-…" value={key} onChange={(e) => setKey(e.target.value)} /></div>
            <div><label className="label">{t("settings.model")}</label>
              <input className="input font-mono" value={s.openai_model} onChange={(e) => setS({ ...s, openai_model: e.target.value })} /></div>
            <div className="flex gap-2">
              <button className="btn-primary" onClick={() => save("ai", key ? { openai_api_key: key } : {})}>{t("app.save")}</button>
              {s.openai_key_set && <button className="btn-danger" onClick={() => save("ai", { openai_api_key: "" })}><Trash2 size={15} /> {t("settings.removeKey")}</button>}
            </div>
          </div>
          {note("ai")}
        </Card>

        <BrandingCard />
        <PosCard />
      </div>
    </>
  );
}

function BrandingCard() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const b = useBranding();
  const [name, setName] = useState(b.app_name);
  const [color, setColor] = useState(b.primary_color);
  const [msg, setMsg] = useState<{ kind: "success" | "danger"; text: string } | null>(null);
  const file = useRef<HTMLInputElement>(null);
  useEffect(() => { setName(b.app_name); setColor(b.primary_color); }, [b.app_name, b.primary_color]);

  const done = () => { setMsg({ kind: "success", text: t("app.saved") }); qc.invalidateQueries({ queryKey: ["branding"] }); };
  const fail = (e: unknown) => setMsg({ kind: "danger", text: (e as Error).message });

  return (
    <Card title={t("settings.branding")}>
      <div className="space-y-4">
        <div className="grid sm:grid-cols-[1fr_auto] gap-4">
          <div><label className="label">{t("settings.appName")}</label><input className="input" value={name} onChange={(e) => setName(e.target.value)} /></div>
          <div><label className="label">{t("settings.color")}</label>
            <div className="flex gap-2"><input type="color" className="h-9 w-12 rounded border border-line cursor-pointer" value={color} onChange={(e) => setColor(e.target.value)} />
              <input className="input w-28 font-mono" value={color} onChange={(e) => setColor(e.target.value)} /></div></div>
        </div>
        <button className="btn-primary" onClick={() => api.put("/branding", { app_name: name, primary_color: color }).then(done, fail)}>{t("app.save")}</button>
        <div className="border-t border-line pt-4">
          <label className="label">{t("settings.logo")}</label>
          <div className="flex items-center gap-4">
            <Logo size={64} />
            <button className="btn-ghost" onClick={() => file.current?.click()}><ImageUp size={16} /> {t("settings.uploadLogo")}</button>
            {b.logo_url && <button className="btn-danger" onClick={() => api.del("/branding/logo").then(done, fail)}><Trash2 size={15} /> {t("settings.removeLogo")}</button>}
            <input ref={file} type="file" hidden accept=".png,.jpg,.jpeg,.webp" onChange={(e) => {
              const f = e.target.files?.[0]; e.target.value = "";
              if (!f) return;
              const fd = new FormData(); fd.append("file", f);
              api.post("/branding/logo", fd).then(done, fail);
            }} />
          </div>
        </div>
        {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      </div>
    </Card>
  );
}

function PosCard() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const keys = useQuery({ queryKey: ["api_keys"], queryFn: () => api.get<any[]>("/integration/keys") });
  const act = useQuery({ queryKey: ["pos_activity"], queryFn: () => api.get("/integration/activity"), refetchInterval: 30_000 });
  const [name, setName] = useState("");
  const [branch, setBranch] = useState("");
  const [created, setCreated] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const create = async () => {
    setErr(null); setCopied(false);
    try {
      const r = await api.post("/integration/keys", { name, branch: branch || null });
      setCreated(r.key); setName(""); setBranch("");
      qc.invalidateQueries({ queryKey: ["api_keys"] });
    } catch (e) { setErr((e as Error).message); }
  };
  const revoke = async (id: number) => {
    if (!confirm(t("pos.revokeConfirm"))) return;
    await api.del(`/integration/keys/${id}`);
    qc.invalidateQueries({ queryKey: ["api_keys"] });
  };
  return (
    <Card title={t("pos.title")} help={t("pos.help")} className="xl:col-span-2">
      <div className="text-sm mb-4">{t("pos.endpoint")}: <code className="bg-surface px-2 py-0.5 rounded">{window.location.origin}/api/v1/pos</code></div>
      <div className="flex flex-wrap gap-3 items-end">
        <div className="flex-1 min-w-48"><label className="label">{t("pos.name")}</label><input className="input" value={name} onChange={(e) => setName(e.target.value)} /></div>
        <div className="flex-1 min-w-48"><label className="label">{t("pos.branch")}</label><input className="input" value={branch} onChange={(e) => setBranch(e.target.value)} /></div>
        <button className="btn-primary" disabled={name.trim().length < 2} onClick={create}><KeyRound size={16} /> {t("pos.create")}</button>
      </div>
      {err && <div className="mt-3"><Notice kind="danger">{err}</Notice></div>}
      {created && (
        <div className="mt-4"><Notice kind="warning">
          <div className="mb-2">{t("pos.shown")}</div>
          <div className="flex gap-2 items-center">
            <code className="bg-white border border-line rounded px-2 py-1 text-xs break-all flex-1">{created}</code>
            <button className="btn-ghost" onClick={() => { navigator.clipboard?.writeText(created); setCopied(true); }}><Copy size={14} /> {copied ? t("pos.copied") : t("ai.copy")}</button>
          </div>
        </Notice></div>
      )}
      <div className="mt-4">
        <DataTable rows={keys.data ?? []} columns={[
          { key: "name", label: t("pos.name").split(" (")[0], render: (r) => <b>{r.name}</b> },
          { key: "branch", label: t("col.branch") },
          { key: "prefix", label: "Key", className: "font-mono text-xs", render: (r) => `${r.prefix}…` },
          { key: "active", label: t("col.status"), render: (r) => r.active ? <Badge kind="active">{t("pos.active")}</Badge> : <Badge kind="inactive">{t("pos.revoked")}</Badge> },
          { key: "last_used_at", label: t("pos.lastUsed"), render: (r) => fmtDate(r.last_used_at, true) },
          { key: "requests", label: t("pos.requests"), num: true, render: (r) => fmtInt(r.requests) },
          { key: "x", label: "", render: (r) => r.active && <button className="text-bad hover:underline text-sm cursor-pointer" onClick={() => revoke(r.id)}>{t("pos.revoke")}</button> },
        ]} />
      </div>
      {act.data && (act.data.branches.length > 0 || act.data.customers?.total > 0) && (
        <div className="mt-5">
          <div className="font-semibold text-sm mb-2">{t("pos.activity")}</div>
          <div className="text-sm text-muted mb-2">{t("pos.customers")}: <b className="text-ink">{fmtInt(act.data.customers?.total)}</b> · {t("pos.last24")}: <b className="text-ink">{fmtInt(act.data.customers?.last_24h)}</b></div>
          <DataTable rows={act.data.branches} columns={[
            { key: "branch", label: t("col.branch") },
            { key: "invoices", label: t("pos.invoices"), num: true, render: (r) => fmtInt(r.invoices) },
            { key: "sales", label: t("col.sales"), num: true, render: (r) => fmtMoney(r.sales) },
            { key: "last_invoice", label: t("pos.lastInvoice"), render: (r) => fmtDate(r.last_invoice, true) },
          ]} />
        </div>
      )}
    </Card>
  );
}
