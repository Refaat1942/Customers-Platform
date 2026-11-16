import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Copy, FolderInput, Loader2, Play, Plus, Send, Trash2, Download } from "lucide-react";
import { api } from "../lib/api";
import { fmtDate, fmtInt } from "../lib/format";
import { Badge, Card, Modal, Notice } from "./ui";
import DataTable from "./DataTable";

type Feed = {
  id?: number; name: string; url: string; auth_type: "none" | "basic" | "bearer" | "header"; username?: string | null;
  secret?: string | null; header_name?: string | null; insecure: boolean; times: string; enabled: boolean;
  last_run_at?: string; last_status?: string; last_message?: string; secret_set?: boolean;
};
const EMPTY: Feed = { name: "SAP daily sales", url: "", auth_type: "basic", username: "", secret: "", header_name: "", insecure: false, times: "06:30", enabled: true };

/** SAP S/4HANA (or any system) sending reports automatically: push API, scheduled pull, drop folder. */
export default function DataFeedsCard() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["feeds"], queryFn: () => api.get("/integration/feeds"), refetchInterval: 20_000 });
  const [edit, setEdit] = useState<Feed | null>(null);
  const [running, setRunning] = useState<number | null>(null);
  const [msg, setMsg] = useState<{ kind: "success" | "danger"; text: string } | null>(null);
  const [copied, setCopied] = useState("");
  const origin = window.location.origin;
  const copy = (k: string, v: string) => { navigator.clipboard?.writeText(v); setCopied(k); setTimeout(() => setCopied(""), 1500); };
  const curl = `curl -X POST "${origin}/api/v1/files?filename=Daily%20Sales.xlsx" \\\n  -H "X-API-Key: cpk_..." \\\n  -H "Content-Type: application/octet-stream" \\\n  --data-binary @"Daily Sales.xlsx"`;

  const run = async (id: number) => {
    setRunning(id); setMsg(null);
    try {
      const r = await api.post(`/integration/feeds/${id}/run`);
      setMsg({ kind: r.ok ? "success" : "danger", text: r.message });
      qc.invalidateQueries({ queryKey: ["feeds"] }); qc.invalidateQueries({ queryKey: ["imports"] });
    } catch (e) { setMsg({ kind: "danger", text: (e as Error).message }); }
    setRunning(null);
  };
  const del = async (id: number) => {
    if (!confirm(t("feeds.deleteConfirm"))) return;
    await api.del(`/integration/feeds/${id}`); qc.invalidateQueries({ queryKey: ["feeds"] });
  };

  return (
    <Card title={t("feeds.title")} help={t("feeds.help")} className="xl:col-span-2">
      <div className="grid lg:grid-cols-3 gap-4">
        {/* 1. push */}
        <div className="rounded-lg border border-line p-4">
          <div className="font-semibold flex items-center gap-2"><Send size={16} className="text-brand" /> 1. {t("feeds.pushTitle")}</div>
          <p className="text-xs text-muted mt-1 mb-3">{t("feeds.pushHelp")}</p>
          <div className="text-xs text-muted">{t("feeds.address")}</div>
          <div className="flex items-center gap-2 mt-1">
            <code className="bg-surface rounded px-2 py-1 text-xs break-all flex-1" dir="ltr">POST {origin}/api/v1/files</code>
            <button className="btn-ghost py-1 px-2" onClick={() => copy("url", `${origin}/api/v1/files`)}><Copy size={13} />{copied === "url" ? "✓" : ""}</button>
          </div>
          <details className="mt-3">
            <summary className="text-xs text-brand cursor-pointer">{t("feeds.example")}</summary>
            <pre className="bg-surface rounded p-2 text-[11px] mt-2 overflow-x-auto" dir="ltr">{curl}</pre>
          </details>
          <div className="text-xs mt-3">{t("feeds.pushKey")}</div>
        </div>
        {/* 2. pull */}
        <div className="rounded-lg border border-line p-4">
          <div className="font-semibold flex items-center gap-2"><Download size={16} className="text-brand" /> 2. {t("feeds.pullTitle")}</div>
          <p className="text-xs text-muted mt-1 mb-3">{t("feeds.pullHelp")}</p>
          <button className="btn-primary" onClick={() => setEdit({ ...EMPTY })}><Plus size={15} /> {t("feeds.add")}</button>
          <div className="text-xs text-muted mt-3">{t("feeds.tz")}: <b dir="ltr">{q.data?.timezone}</b></div>
        </div>
        {/* 3. inbox */}
        <div className="rounded-lg border border-line p-4">
          <div className="font-semibold flex items-center gap-2"><FolderInput size={16} className="text-brand" /> 3. {t("feeds.inboxTitle")}</div>
          <p className="text-xs text-muted mt-1 mb-3">{t("feeds.inboxHelp")}</p>
          <code className="bg-surface rounded px-2 py-1 text-xs block" dir="ltr">/opt/customers-platform/inbox</code>
          <div className="text-xs text-muted mt-2">{t("feeds.inboxAfter")}</div>
        </div>
      </div>

      {msg && <div className="mt-4"><Notice kind={msg.kind}>{msg.text}</Notice></div>}

      {(q.data?.feeds ?? []).length > 0 && (
        <div className="mt-5">
          <div className="font-semibold text-sm mb-2">{t("feeds.list")}</div>
          <DataTable rows={q.data.feeds} noExport columns={[
            { key: "name", label: t("feeds.name"), render: (r: Feed) => <b>{r.name}</b> },
            { key: "url", label: t("feeds.url"), className: "max-w-72 truncate font-mono text-xs", render: (r: Feed) => <span dir="ltr" title={r.url}>{r.url}</span> },
            { key: "times", label: t("feeds.times"), render: (r: Feed) => <span dir="ltr">{r.times}</span> },
            { key: "enabled", label: t("col.status"), render: (r: Feed) => r.enabled ? <Badge kind="active">{t("feeds.on")}</Badge> : <Badge>{t("feeds.off")}</Badge> },
            { key: "last_run_at", label: t("feeds.lastRun"), render: (r: Feed) => r.last_run_at ? <span>{fmtDate(r.last_run_at, true)} {r.last_status && <Badge kind={r.last_status === "ok" ? "active" : r.last_status === "running" ? "attention" : "inactive"}>{r.last_status}</Badge>}</span> : "–" },
            { key: "last_message", label: t("feeds.result"), className: "max-w-80 text-xs", render: (r: Feed) => <span className="line-clamp-2" title={r.last_message ?? ""}>{r.last_message ?? "–"}</span> },
            { key: "x", label: "", render: (r: Feed) => (
              <span className="flex gap-1 justify-end whitespace-nowrap">
                <button className="btn-ghost py-1 px-2 text-xs" disabled={running === r.id} onClick={() => run(r.id!)}>
                  {running === r.id ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />} {t("feeds.runNow")}</button>
                <button className="btn-ghost py-1 px-2 text-xs" onClick={() => setEdit({ ...r, secret: null })}>{t("app.edit")}</button>
                <button className="text-bad p-1 cursor-pointer" onClick={() => del(r.id!)}><Trash2 size={14} /></button>
              </span>
            ) },
          ]} />
        </div>
      )}

      {(q.data?.recent ?? []).length > 0 && (
        <div className="mt-5">
          <div className="font-semibold text-sm mb-2">{t("feeds.recent")}</div>
          <DataTable rows={q.data.recent} maxHeight={300} columns={[
            { key: "id", label: "#", num: true },
            { key: "created_at", label: t("feeds.when"), render: (r: any) => fmtDate(r.created_at, true) },
            { key: "created_by", label: t("feeds.source"), render: (r: any) => <span dir="ltr">{r.created_by}</span> },
            { key: "filename", label: t("feeds.file"), className: "max-w-64 truncate" },
            { key: "status", label: t("col.status"), render: (r: any) => <span title={r.message ?? ""}><Badge kind={r.status === "done" ? "active" : r.status === "running" ? "attention" : "inactive"}>{r.status}</Badge></span> },
            { key: "rows_imported", label: t("feeds.added"), num: true, render: (r: any) => fmtInt(r.rows_imported) },
            { key: "rows_skipped", label: t("feeds.skipped"), num: true, render: (r: any) => fmtInt(r.rows_skipped) },
            { key: "message", label: "", className: "max-w-72 text-xs text-muted truncate" },
          ]} />
        </div>
      )}

      {edit && <FeedForm feed={edit} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); qc.invalidateQueries({ queryKey: ["feeds"] }); }} />}
    </Card>
  );
}

function FeedForm({ feed, onClose, onSaved }: { feed: Feed; onClose: () => void; onSaved: () => void }) {
  const { t } = useTranslation();
  const [f, setF] = useState<Feed>(feed);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (p: Partial<Feed>) => setF((x) => ({ ...x, ...p }));
  const save = async () => {
    setBusy(true); setErr(null);
    const body = { name: f.name, url: f.url, auth_type: f.auth_type, username: f.username || null, header_name: f.header_name || null,
      insecure: f.insecure, times: f.times, enabled: f.enabled, secret: f.secret === null ? null : f.secret ?? "" };
    try {
      if (f.id) await api.put(`/integration/feeds/${f.id}`, body); else await api.post("/integration/feeds", body);
      onSaved();
    } catch (e) { setErr((e as Error).message); }
    setBusy(false);
  };
  return (
    <Modal title={f.id ? t("feeds.editTitle") : t("feeds.add")} onClose={onClose} wide>
      <div className="grid sm:grid-cols-2 gap-4">
        <div><label className="label">{t("feeds.name")}</label><input className="input" value={f.name} onChange={(e) => set({ name: e.target.value })} /></div>
        <div><label className="label">{t("feeds.times")}</label><input className="input" dir="ltr" value={f.times} placeholder="06:30, 14:00" onChange={(e) => set({ times: e.target.value })} />
          <div className="text-xs text-muted mt-1">{t("feeds.timesHelp")}</div></div>
        <div className="sm:col-span-2"><label className="label">{t("feeds.url")}</label>
          <input className="input font-mono text-xs" dir="ltr" value={f.url} placeholder="https://sap-host:44300/sap/opu/odata/sap/ZSD_DAILY_SALES_SRV/Sales?$format=json&$filter=BillingDate eq datetime'{yesterday}T00:00:00'" onChange={(e) => set({ url: e.target.value })} />
          <div className="text-xs text-muted mt-1">{t("feeds.urlHelp")}</div></div>
        <div><label className="label">{t("feeds.auth")}</label>
          <select className="input" value={f.auth_type} onChange={(e) => set({ auth_type: e.target.value as Feed["auth_type"] })}>
            {(["basic", "bearer", "header", "none"] as const).map((a) => <option key={a} value={a}>{t(`feeds.authTypes.${a}`)}</option>)}
          </select></div>
        {f.auth_type === "basic" && <div><label className="label">{t("feeds.user")}</label><input className="input" dir="ltr" value={f.username ?? ""} onChange={(e) => set({ username: e.target.value })} /></div>}
        {f.auth_type === "header" && <div><label className="label">{t("feeds.headerName")}</label><input className="input" dir="ltr" value={f.header_name ?? ""} placeholder="APIKey" onChange={(e) => set({ header_name: e.target.value })} /></div>}
        {f.auth_type !== "none" && (
          <div><label className="label">{f.auth_type === "basic" ? t("feeds.password") : t("feeds.token")}</label>
            <input className="input" type="password" autoComplete="new-password" dir="ltr" value={f.secret ?? ""} placeholder={f.secret === null && f.secret_set ? t("feeds.keep") : ""}
              onChange={(e) => set({ secret: e.target.value })} /></div>
        )}
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="accent-brand" checked={f.enabled} onChange={(e) => set({ enabled: e.target.checked })} /> {t("feeds.enabled")}</label>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="accent-brand" checked={f.insecure} onChange={(e) => set({ insecure: e.target.checked })} /> {t("feeds.insecure")}</label>
      </div>
      {err && <div className="mt-3"><Notice kind="danger">{err}</Notice></div>}
      <div className="flex justify-end gap-2 mt-5">
        <button className="btn-ghost" onClick={onClose}>{t("app.cancel")}</button>
        <button className="btn-primary" disabled={busy || f.name.length < 2 || !/^https?:\/\//.test(f.url)} onClick={save}>{busy && <Loader2 size={15} className="animate-spin" />} {t("app.save")}</button>
      </div>
    </Modal>
  );
}
