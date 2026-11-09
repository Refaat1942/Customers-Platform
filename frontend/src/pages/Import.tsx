import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import clsx from "clsx";
import { CheckCircle2, FileSpreadsheet, Loader2, Trash2, UploadCloud, XCircle } from "lucide-react";
import { api, getToken } from "../lib/api";
import { fmtBytes, fmtDate, fmtInt } from "../lib/format";
import DataTable from "../components/DataTable";
import { Badge, Card, Notice, PageHeader } from "../components/ui";

type Kind = "sales" | "customers" | "skip" | "empty";
type SheetInfo = {
  sheet: string | null; rows: number | null; columns: string[]; kind: Kind; kind_reason: string;
  mappings: Record<"sales" | "customers", Record<string, string | null>>; sample: Record<string, any>[];
};
type Preview = {
  upload_id: string; filename: string; sheets_info: SheetInfo[];
  fields: Record<"sales" | "customers", string[]>; required: Record<"sales" | "customers", string[]>;
  modes: Record<"sales" | "customers", string[]>; duplicate_of: { id: number; finished_at: string } | null;
};
type SheetState = SheetInfo & { mode: Record<"sales" | "customers", string>; open: boolean };

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
  const [sheets, setSheets] = useState<SheetState[]>([]);
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
      setPv(p);
      setSheets(p.sheets_info.map((x, i) => ({ ...x, mode: { sales: "merge", customers: "upsert" }, open: i === 0 || p.sheets_info.length <= 2 })));
      setPhase("mapping");
    } catch (e) { setErr((e as Error).message); setPhase("idle"); }
  };

  const update = (i: number, patch: Partial<SheetState>) => setSheets((all) => all.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  const setField = (i: number, kind: "sales" | "customers", f: string, v: string | null) =>
    setSheets((all) => all.map((x, j) => (j === i ? { ...x, mappings: { ...x.mappings, [kind]: { ...x.mappings[kind], [f]: v } } } : x)));
  const active = sheets.filter((x) => x.kind === "sales" || x.kind === "customers");
  const missingOf = (x: SheetState) => (x.kind === "sales" || x.kind === "customers") && pv
    ? pv.required[x.kind].filter((f) => !x.mappings[x.kind as "sales"]?.[f]) : [];
  const blocked = active.length === 0 || active.some((x) => missingOf(x).length > 0);

  const commit = async () => {
    if (!pv) return;
    if (active.some((x) => x.mode[x.kind as "sales"] === "replace_all") && !confirm(t("imp.modes.replace_all") + "?")) return;
    setErr(null); setPhase("importing");
    try {
      await api.post("/imports/commit", {
        upload_id: pv.upload_id,
        jobs: active.map((x) => ({ sheet: x.sheet, kind: x.kind, mapping: x.mappings[x.kind as "sales"], mode: x.mode[x.kind as "sales"] })),
      });
      setPv(null); setSheets([]); setFile(null); setPhase("idle");
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
            {sheets.length > 1 && <div className="text-sm font-semibold mb-3">{t("imp.sheetsFound", { n: sheets.length })}</div>}
            <div className="space-y-4">
              {sheets.map((x, i) => {
                const k = x.kind === "sales" || x.kind === "customers" ? x.kind : null;
                const missing = missingOf(x);
                return (
                  <div key={i} className={clsx("rounded-lg border p-4", k ? "border-line" : "border-dashed border-line bg-surface/50")}>
                    <div className="flex flex-wrap items-center gap-3">
                      <FileSpreadsheet size={18} className="text-brand" />
                      <span className="font-semibold">{x.sheet ?? pv.filename}</span>
                      {x.rows != null && <span className="text-xs text-muted">{t("imp.rowsApprox", { n: fmtInt(x.rows) })}</span>}
                      <span className="text-xs text-muted">· {x.columns.length} cols</span>
                      <div className="ms-auto flex items-center gap-2">
                        <span className="text-xs text-muted">{t("imp.kind")}</span>
                        <select className="input py-1.5 w-auto" value={x.kind} disabled={x.kind === "empty"}
                          onChange={(e) => update(i, { kind: e.target.value as Kind, open: e.target.value !== "skip" })}>
                          {(x.kind === "empty" ? ["empty"] : ["sales", "customers", "skip"]).map((o) => <option key={o} value={o}>{t(`imp.kinds.${o}`)}</option>)}
                        </select>
                      </div>
                    </div>
                    <div className={clsx("text-xs mt-2", x.kind_reason === "unknown" ? "text-warn" : "text-good")}>{t(`imp.kindReason.${x.kind_reason}`)}</div>
                    {k && (
                      <>
                        {!x.open && missing.length === 0 ? (
                          <button className="text-sm text-brand underline mt-2 cursor-pointer" onClick={() => update(i, { open: true })}>{t("imp.mapping")}</button>
                        ) : (
                          <>
                            <div className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-3 mt-3">
                              {pv.fields[k].map((f) => (
                                <div key={f}>
                                  <label className="label">{t(`imp.fields.${f}`)}{pv.required[k].includes(f) && <span className="text-bad"> *</span>}</label>
                                  <select className={clsx("input", pv.required[k].includes(f) && !x.mappings[k]?.[f] && "border-bad", x.mappings[k]?.[f] && "bg-brand-soft/40")}
                                    value={x.mappings[k]?.[f] ?? ""} onChange={(e) => setField(i, k, f, e.target.value || null)}>
                                    <option value="">{t("imp.notMapped")}</option>
                                    {x.columns.map((c) => <option key={c} value={c}>{c}</option>)}
                                  </select>
                                </div>
                              ))}
                            </div>
                            <details className="mt-3">
                              <summary className="text-sm text-muted cursor-pointer">{t("imp.showSample")}</summary>
                              <div className="mt-2">
                                <DataTable rows={x.sample.slice(0, 8)} maxHeight={260}
                                  columns={x.columns.map((c) => ({ key: c, label: c, render: (r: any) => (r[c] == null ? "" : String(r[c])) }))} />
                              </div>
                            </details>
                          </>
                        )}
                        <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2">
                          {pv.modes[k].map((m) => (
                            <label key={m} className={clsx("flex items-center gap-2 text-sm cursor-pointer", m === "replace_all" && "text-bad", m === "replace_period" && "text-warn")}>
                              <input type="radio" className="accent-brand" checked={x.mode[k] === m} onChange={() => update(i, { mode: { ...x.mode, [k]: m } })} /> {t(`imp.modes.${m}`)}
                            </label>
                          ))}
                        </div>
                      </>
                    )}
                  </div>
                );
              })}
            </div>
            <div className="flex gap-2 mt-5">
              <button className="btn-primary" disabled={blocked || phase === "importing"} onClick={commit}>
                {phase === "importing" && <Loader2 size={16} className="animate-spin" />} {t("imp.importAll", { n: active.length })}
              </button>
              <button className="btn-ghost" onClick={() => { setPv(null); setSheets([]); setPhase("idle"); }}>{t("app.cancel")}</button>
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
            { key: "kind", label: t("imp.kind"), render: (r) => <Badge>{t(`imp.kinds.${r.kind ?? "sales"}`)}</Badge> },
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
