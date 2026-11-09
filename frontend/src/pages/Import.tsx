import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import clsx from "clsx";
import { CheckCircle2, FileSpreadsheet, Loader2, Trash2, UploadCloud, XCircle } from "lucide-react";
import { api, getToken } from "../lib/api";
import { fmtBytes, fmtDate, fmtInt } from "../lib/format";
import DataTable from "../components/DataTable";
import { Badge, Card, Notice, PageHeader } from "../components/ui";

type Preview = {
  upload_id: string; filename: string; sheets: string[]; sheet: string | null; columns: string[];
  mapping: Record<string, string | null>; sample: Record<string, any>[]; fields: string[]; required: string[];
  modes: string[]; duplicate_of: { id: number; finished_at: string } | null;
};

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Upload in 8 MB pieces. A failed piece is retried (up to 6 times, with back-off) and the
 *  upload always resumes from the number of bytes the server says it has. */
async function chunkedUpload(file: File, onProgress: (sent: number) => void): Promise<string> {
  const init = await api.post("/imports/uploads", { filename: file.name, size: file.size });
  const id: string = init.upload_id;
  const size: number = init.chunk_size;
  let offset = 0;
  let failures = 0;
  while (offset < file.size) {
    try {
      const res = await fetch(`/api/imports/uploads/${id}?offset=${offset}`, {
        method: "PUT", body: file.slice(offset, offset + size),
        headers: { Authorization: `Bearer ${getToken()}`, "Content-Type": "application/octet-stream" },
      });
      if (res.ok) { offset = (await res.json()).received; failures = 0; onProgress(offset); continue; }
      if (res.status !== 409) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
    } catch (e) {
      if (++failures > 6) throw e;
      await sleep(1000 * 2 ** failures);
    }
    offset = (await api.get(`/imports/uploads/${id}`)).received;  // resume point
    onProgress(offset);
  }
  return id;
}

export default function Import() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [sent, setSent] = useState(0);
  const [phase, setPhase] = useState<"idle" | "uploading" | "reading" | "mapping" | "importing">("idle");
  const [err, setErr] = useState<string | null>(null);
  const [pv, setPv] = useState<Preview | null>(null);
  const [mapping, setMapping] = useState<Record<string, string | null>>({});
  const [mode, setMode] = useState("replace_period");
  const [drag, setDrag] = useState(false);

  const history = useQuery({
    queryKey: ["imports"], queryFn: () => api.get<any[]>("/imports"),
    refetchInterval: (q) => (q.state.data?.some((i) => i.status === "running") ? 1500 : false),
  });
  const running = history.data?.find((i) => i.status === "running");

  const start = async (f: File) => {
    setFile(f); setErr(null); setPv(null); setSent(0); setPhase("uploading");
    try {
      const id = await chunkedUpload(f, setSent);
      setPhase("reading");
      const p = await api.post<Preview>(`/imports/uploads/${id}/finish`);
      setPv(p); setMapping(p.mapping); setPhase("mapping");
    } catch (e) { setErr((e as Error).message); setPhase("idle"); }
  };

  const changeSheet = async (sheet: string) => {
    if (!pv) return;
    try {
      const p = await api.get(`/imports/uploads/${pv.upload_id}/preview`, { sheet });
      setPv({ ...pv, ...p }); setMapping(p.mapping);
    } catch (e) { setErr((e as Error).message); }
  };

  const commit = async () => {
    if (!pv) return;
    if (mode === "replace_all" && !confirm(t("imp.modes.replace_all") + "?")) return;
    setErr(null); setPhase("importing");
    try {
      await api.post("/imports/commit", { upload_id: pv.upload_id, mapping, mode, sheet: pv.sheet });
      setPv(null); setFile(null); setPhase("idle");
      qc.invalidateQueries({ queryKey: ["imports"] });
    } catch (e) { setErr((e as Error).message); setPhase("mapping"); }
  };

  const undo = async (id: number) => {
    if (!confirm(t("imp.undoConfirm"))) return;
    await api.del(`/imports/${id}`);
    qc.invalidateQueries();
  };

  // refresh all dashboards when an import finishes
  const prevRunning = useRef<number | null>(null);
  if (prevRunning.current && !running) { prevRunning.current = null; setTimeout(() => qc.invalidateQueries(), 0); }
  if (running) prevRunning.current = running.id;

  const missing = pv?.required.filter((f) => !mapping[f]) ?? [];

  return (
    <>
      <PageHeader title={t("imp.title")} subtitle={t("imp.subtitle")} />
      <div className="space-y-5">
        {err && <Notice kind="danger">{err}</Notice>}

        {phase === "idle" && (
          <div onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files[0]; if (f) start(f); }}
            onClick={() => input.current?.click()}
            className={clsx("card border-2 border-dashed p-10 text-center cursor-pointer transition", drag ? "border-brand bg-brand-soft" : "hover:border-brand")}>
            <UploadCloud size={40} className="mx-auto text-brand" />
            <div className="font-semibold mt-3">{t("imp.drop")}</div>
            <div className="text-xs text-muted mt-1">.xlsx · .xls · .xlsb · .csv · .zip</div>
            <div className="text-xs text-muted mt-3">{t("imp.tip")}</div>
            <input ref={input} type="file" hidden accept=".xlsx,.xlsm,.xls,.xlsb,.csv,.zip"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) start(f); e.target.value = ""; }} />
          </div>
        )}

        {(phase === "uploading" || phase === "reading") && file && (
          <Card>
            <div className="flex items-center gap-3 mb-3">
              <FileSpreadsheet className="text-brand" />
              <div className="flex-1">
                <div className="font-semibold">{file.name}</div>
                <div className="text-xs text-muted">{phase === "uploading" ? `${t("imp.uploading")} ${fmtBytes(sent)} / ${fmtBytes(file.size)}` : t("imp.processing")}</div>
              </div>
              <Loader2 className="animate-spin text-muted" />
            </div>
            <div className="h-2.5 bg-surface rounded-full overflow-hidden">
              <div className="h-full bg-brand transition-all" style={{ width: `${phase === "reading" ? 100 : (100 * sent) / file.size}%` }} />
            </div>
          </Card>
        )}

        {(phase === "mapping" || phase === "importing") && pv && (
          <Card title={`${t("imp.mapping")} — ${pv.filename}`} help={t("imp.mappingHelp")}>
            {pv.duplicate_of && <div className="mb-4"><Notice kind="warning">{t("imp.duplicate", { id: pv.duplicate_of.id, date: fmtDate(pv.duplicate_of.finished_at) })}</Notice></div>}
            {pv.sheets.length > 1 && (
              <div className="mb-4 max-w-xs">
                <label className="label">{t("imp.sheet")}</label>
                <select className="input" value={pv.sheet ?? ""} onChange={(e) => changeSheet(e.target.value)}>
                  {pv.sheets.map((s) => <option key={s}>{s}</option>)}
                </select>
              </div>
            )}
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-3">
              {pv.fields.map((f) => (
                <div key={f}>
                  <label className="label">{t(`imp.fields.${f}`)}{pv.required.includes(f) && <span className="text-bad"> *</span>}</label>
                  <select className={clsx("input", pv.required.includes(f) && !mapping[f] && "border-bad", mapping[f] && "bg-brand-soft/40")}
                    value={mapping[f] ?? ""} onChange={(e) => setMapping({ ...mapping, [f]: e.target.value || null })}>
                    <option value="">{t("imp.notMapped")}</option>
                    {pv.columns.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
              ))}
            </div>

            <div className="mt-5">
              <div className="label">{t("imp.preview")}</div>
              <DataTable rows={pv.sample.slice(0, 8)} maxHeight={260}
                columns={pv.columns.map((c) => ({ key: c, label: c, render: (r: any) => (r[c] == null ? "" : String(r[c])) }))} />
            </div>

            <div className="mt-5">
              <div className="label">{t("imp.mode")}</div>
              <div className="space-y-2">
                {pv.modes.map((m) => (
                  <label key={m} className={clsx("flex items-center gap-2 text-sm cursor-pointer", m === "replace_all" && "text-bad")}>
                    <input type="radio" className="accent-brand" checked={mode === m} onChange={() => setMode(m)} /> {t(`imp.modes.${m}`)}
                  </label>
                ))}
              </div>
            </div>
            <div className="flex gap-2 mt-5">
              <button className="btn-primary" disabled={missing.length > 0 || phase === "importing"} onClick={commit}>
                {phase === "importing" && <Loader2 size={16} className="animate-spin" />} {t("imp.start")}
              </button>
              <button className="btn-ghost" onClick={() => { setPv(null); setPhase("idle"); }}>{t("app.cancel")}</button>
            </div>
          </Card>
        )}

        <Card title={t("imp.history")}>
          {running && (
            <div className="mb-4 rounded-lg border border-line p-4">
              <div className="flex justify-between text-sm mb-2">
                <span className="font-semibold">#{running.id} {running.filename}</span>
                <span className="text-muted">{t(`imp.stage.${running.stage ?? "queued"}`)} · {fmtInt(running.rows_read)} {t("app.rows")} · {Math.round(running.progress)}%</span>
              </div>
              <div className="h-2.5 bg-surface rounded-full overflow-hidden">
                <div className="h-full bg-brand transition-all" style={{ width: `${running.progress}%` }} />
              </div>
            </div>
          )}
          <DataTable rows={history.data ?? []} maxHeight={520} columns={[
            { key: "id", label: "#", num: true },
            { key: "filename", label: "File", className: "max-w-56 truncate" },
            { key: "status", label: t("col.status"), render: (r) => r.status === "done" ? <Badge kind="active"><CheckCircle2 size={12} /> OK</Badge>
              : r.status === "failed" ? <span title={r.message}><Badge kind="inactive"><XCircle size={12} /> {r.message?.slice(0, 40)}</Badge></span>
              : r.status === "running" ? <Badge kind="attention">{Math.round(r.progress)}%</Badge> : <Badge>{r.status}</Badge> },
            { key: "mode", label: t("imp.mode"), render: (r) => <span className="text-xs">{t(`imp.modes.${r.mode}`).split("(")[0]}</span> },
            { key: "rows_imported", label: t("imp.imported"), num: true, render: (r) => fmtInt(r.rows_imported) },
            { key: "rows_replaced", label: t("imp.replaced"), num: true, render: (r) => fmtInt(r.rows_replaced) },
            { key: "rows_skipped", label: t("imp.skipped"), num: true, render: (r) => fmtInt(r.rows_skipped) },
            { key: "invalid_phones", label: t("imp.invalidPhones"), num: true, render: (r) => fmtInt(r.invalid_phones) },
            { key: "date_from", label: t("filters.dateRange"), render: (r) => r.date_from ? `${fmtDate(r.date_from)} → ${fmtDate(r.date_to)}` : "–" },
            { key: "created_by", label: t("audit.user") },
            { key: "created_at", label: t("audit.time"), render: (r) => fmtDate(r.created_at, true) },
            { key: "x", label: "", render: (r) => r.status === "done" && <button className="text-bad hover:underline cursor-pointer" title={t("imp.undo")} onClick={() => undo(r.id)}><Trash2 size={15} /></button> },
          ]} />
        </Card>
      </div>
    </>
  );
}
