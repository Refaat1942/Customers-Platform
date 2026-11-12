import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import clsx from "clsx";
import { CheckCircle2, Clock, FileSpreadsheet, Loader2, Trash2, UploadCloud, XCircle } from "lucide-react";
import { api, getToken } from "../lib/api";
import { fmtBytes, fmtDate, fmtInt } from "../lib/format";
import DataTable from "../components/DataTable";
import { Badge, Card, Notice, PageHeader } from "../components/ui";

type Kind = "sales" | "customers" | "skip" | "empty";
type SheetInfo = {
  sheet: string | null; rows: number | null; columns: string[]; kind: Kind; kind_reason: string; warnings?: string[];
  date_order?: "dmy" | "mdy"; date_order_sure?: boolean; text_dates?: boolean;
  mappings: Record<"sales" | "customers", Record<string, string | null>>; sample: Record<string, any>[];
};
type Preview = {
  upload_id: string; filename: string; sheets_info: SheetInfo[];
  fields: Record<"sales" | "customers", string[]>; required: Record<"sales" | "customers", string[]>;
  modes: Record<"sales" | "customers", string[]>; duplicate_of: { id: number; finished_at: string } | null;
};
type SheetState = SheetInfo & { mode: Record<"sales" | "customers", string>; open: boolean; fileIdx: number };
type FileState = { name: string; size: number; sent: number; status: "waiting" | "uploading" | "reading" | "ready" | "error"; err?: string; pv?: Preview };

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
  const [files, setFiles] = useState<FileState[]>([]);
  const [phase, setPhase] = useState<"idle" | "files" | "importing">("idle");
  const [err, setErr] = useState<string | null>(null);
  const [sheets, setSheets] = useState<SheetState[]>([]);
  const [drag, setDrag] = useState(false);
  const meta = files.find((f) => f.pv)?.pv;
  const busy = files.some((f) => f.status === "waiting" || f.status === "uploading" || f.status === "reading");

  const history = useQuery({
    queryKey: ["imports"], queryFn: () => api.get<any[]>("/imports"),
    refetchInterval: (q) => (q.state.data?.some((i) => i.status === "running") ? 1500 : false),
  });
  const running = history.data?.find((i) => i.status === "running");

  /** Several files: uploaded one after another, each analysed sheet by sheet. */
  const start = async (list: File[]) => {
    if (!list.length) return;
    setErr(null); setPhase("files");
    const base = files.length;
    setFiles((fs) => [...fs, ...list.map((f) => ({ name: f.name, size: f.size, sent: 0, status: "waiting" as const }))]);
    const patch = (i: number, p: Partial<FileState>) => setFiles((fs) => fs.map((x, j) => (j === i ? { ...x, ...p } : x)));
    for (let n = 0; n < list.length; n++) {
      const idx = base + n;
      try {
        patch(idx, { status: "uploading" });
        const id = await chunkedUpload(list[n], (sent) => patch(idx, { sent }));
        patch(idx, { status: "reading" });
        const p = await api.post<Preview>(`/imports/uploads/${id}/finish`);
        patch(idx, { status: "ready", pv: p });
        setSheets((all) => [...all, ...p.sheets_info.map((x, i) => ({
          ...x, fileIdx: idx, mode: { sales: "merge", customers: "upsert" },
          open: x.kind_reason === "unknown" || (list.length === 1 && (i === 0 || p.sheets_info.length <= 2)),
        }))]);
      } catch (e) { patch(idx, { status: "error", err: (e as Error).message }); }
    }
  };

  const reset = () => { setFiles([]); setSheets([]); setPhase("idle"); };

  const update = (i: number, patch: Partial<SheetState>) => setSheets((all) => all.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  const setField = (i: number, kind: "sales" | "customers", f: string, v: string | null) =>
    setSheets((all) => all.map((x, j) => (j === i ? { ...x, mappings: { ...x.mappings, [kind]: { ...x.mappings[kind], [f]: v } } } : x)));
  const active = sheets.filter((x) => x.kind === "sales" || x.kind === "customers");
  const missingOf = (x: SheetState) => (x.kind === "sales" || x.kind === "customers") && meta
    ? meta.required[x.kind].filter((f) => !x.mappings[x.kind as "sales"]?.[f]) : [];
  const blocked = busy || active.length === 0 || active.some((x) => missingOf(x).length > 0);

  const commit = async () => {
    if (active.some((x) => x.mode[x.kind as "sales"] === "replace_all") && !confirm(t("imp.modes.replace_all") + "?")) return;
    setErr(null); setPhase("importing");
    const errors: string[] = [];
    // one request per file; the server runs all imports one after another
    for (const [i, f] of files.entries()) {
      const jobs = active.filter((x) => x.fileIdx === i);
      if (!f.pv || !jobs.length) continue;
      try {
        await api.post("/imports/commit", {
          upload_id: f.pv.upload_id,
          jobs: jobs.map((x) => ({ sheet: x.sheet, kind: x.kind, mapping: x.mappings[x.kind as "sales"], mode: x.mode[x.kind as "sales"], date_order: x.date_order ?? "dmy" })),
        });
      } catch (e) { errors.push(`${f.name}: ${(e as Error).message}`); }
    }
    qc.invalidateQueries({ queryKey: ["imports"] });
    if (errors.length) { setErr(errors.join(" · ")); setPhase("files"); } else reset();
  };

  const cancelImport = async (id: number) => {
    if (!confirm(t("imp.cancelConfirm"))) return;
    try { await api.post(`/imports/${id}/cancel`); } catch (e) { setErr((e as Error).message); }
    qc.invalidateQueries({ queryKey: ["imports"] });
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

        {phase !== "importing" && (
          <div onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); start(Array.from(e.dataTransfer.files)); }}
            onClick={() => input.current?.click()}
            className={clsx("card border-2 border-dashed text-center cursor-pointer transition", files.length ? "p-5" : "p-10", drag ? "border-brand bg-brand-soft" : "hover:border-brand")}>
            <UploadCloud size={40} className="mx-auto text-brand" />
            <div className="font-semibold mt-3">{t("imp.drop")}</div>
            <div className="text-xs text-muted mt-1">.xlsx · .xls · .xlsb · .csv · .zip</div>
            <div className="text-xs text-muted mt-3">{t("imp.tip")}</div>
            <input ref={input} type="file" hidden multiple accept=".xlsx,.xlsm,.xls,.xlsb,.csv,.zip"
              onChange={(e) => { start(Array.from(e.target.files ?? [])); e.target.value = ""; }} />
          </div>
        )}

        {files.length > 0 && (
          <Card>
            <div className="space-y-3">
              {files.map((f, i) => (
                <div key={i}>
                  <div className="flex items-center gap-3 text-sm">
                    <FileSpreadsheet size={18} className="text-brand shrink-0" />
                    <span className="font-semibold truncate">{f.name}</span>
                    <span className="text-xs text-muted">{fmtBytes(f.size)}</span>
                    <span className="ms-auto text-xs">
                      {f.status === "ready" ? <span className="text-good inline-flex items-center gap-1"><CheckCircle2 size={14} /> {t("imp.sheetsFound", { n: f.pv?.sheets_info.length ?? 0 })}</span>
                        : f.status === "error" ? <span className="text-bad">{f.err}</span>
                        : f.status === "waiting" ? <span className="text-muted">…</span>
                        : <span className="text-muted inline-flex items-center gap-1"><Loader2 size={14} className="animate-spin" />
                            {f.status === "uploading" ? `${t("imp.uploading")} ${fmtBytes(f.sent)} / ${fmtBytes(f.size)}` : t("imp.processing")}</span>}
                    </span>
                  </div>
                  {(f.status === "uploading" || f.status === "reading") && (
                    <div className="h-1.5 bg-surface rounded-full overflow-hidden mt-2">
                      <div className="h-full bg-brand transition-all" style={{ width: `${f.status === "reading" ? 100 : (100 * f.sent) / f.size}%` }} />
                    </div>
                  )}
                  {f.pv?.duplicate_of && <div className="mt-2"><Notice kind="warning">{f.name}: {t("imp.duplicate", { id: f.pv.duplicate_of.id, date: fmtDate(f.pv.duplicate_of.finished_at) })}</Notice></div>}
                </div>
              ))}
            </div>
          </Card>
        )}

        {sheets.length > 0 && meta && (
          <Card title={t("imp.mapping")} help={t("imp.mappingHelp")}>
            {sheets.length > 1 && <div className="text-sm font-semibold mb-3">{t("imp.sheetsFound", { n: sheets.length })}</div>}
            <div className="space-y-4">
              {sheets.map((x, i) => {
                const k = x.kind === "sales" || x.kind === "customers" ? x.kind : null;
                const missing = missingOf(x);
                return (
                  <div key={i} className={clsx("rounded-lg border p-4", k ? "border-line" : "border-dashed border-line bg-surface/50")}>
                    <div className="flex flex-wrap items-center gap-3">
                      <FileSpreadsheet size={18} className="text-brand" />
                      <span className="font-semibold">{files.length > 1 && <span className="text-muted font-normal">{files[x.fileIdx]?.name} › </span>}{x.sheet ?? files[x.fileIdx]?.name}</span>
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
                    {k === "sales" && x.text_dates && (
                      <div className={clsx("mt-3 rounded-lg border p-3 text-sm flex flex-wrap items-center gap-3", x.date_order_sure ? "border-line" : "border-amber-300 bg-amber-50")}>
                        <span className="font-medium">{t("imp.dateOrder")}</span>
                        {(["dmy", "mdy"] as const).map((o) => (
                          <label key={o} className="flex items-center gap-2 cursor-pointer">
                            <input type="radio" className="accent-brand" checked={(x.date_order ?? "dmy") === o} onChange={() => update(i, { date_order: o, date_order_sure: true })} />
                            {t(`imp.dateOrders.${o}`)}
                          </label>
                        ))}
                        {!x.date_order_sure && <span className="text-xs text-warn w-full">{t("imp.dateOrderAsk")}</span>}
                      </div>
                    )}
                    {k === "sales" && (x.warnings ?? []).map((w) => (
                      <div key={w} className="mt-2"><Notice kind={w === "time_not_mapped" ? "info" : "warning"}>{t(`imp.warn.${w}`)}</Notice></div>
                    ))}
                    {k && (
                      <>
                        {!x.open && missing.length === 0 ? (
                          <button className="text-sm text-brand underline mt-2 cursor-pointer" onClick={() => update(i, { open: true })}>{t("imp.mapping")}</button>
                        ) : (
                          <>
                            <div className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-3 mt-3">
                              {meta.fields[k].map((f) => (
                                <div key={f}>
                                  <label className="label">{t(`imp.fields.${f}`)}{meta.required[k].includes(f) && <span className="text-bad"> *</span>}</label>
                                  <select className={clsx("input", meta.required[k].includes(f) && !x.mappings[k]?.[f] && "border-bad", x.mappings[k]?.[f] && "bg-brand-soft/40")}
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
                          {meta.modes[k].map((m) => (
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
              <button className="btn-ghost" onClick={reset}>{t("app.cancel")}</button>
            </div>
          </Card>
        )}

        <DuplicatesCard />

        <Card title={t("imp.history")} help={t("imp.skippedHelp")}>
          {(() => {
            const active = (history.data ?? []).filter((i) => i.status === "running").sort((x, y) => x.id - y.id);
            const working = active.find((i) => i.stage && i.stage !== "queued");
            return active.length > 0 && (
              <div className="mb-4 space-y-2">
                {active.map((r) => {
                  const waiting = !r.stage || r.stage === "queued";
                  return (
                    <div key={r.id} className={clsx("rounded-lg border p-4", waiting ? "border-dashed border-line bg-surface/40" : "border-line")}>
                      <div className="flex flex-wrap items-center gap-3 text-sm mb-2">
                        {waiting ? <Clock size={15} className="text-muted" /> : <Loader2 size={15} className="animate-spin text-brand" />}
                        <span className="font-semibold">#{r.id} {r.filename}</span>
                        <span className="text-muted ms-auto">
                          {waiting
                            ? (working ? t("imp.waitingFor", { id: working.id }) : t("imp.stage.queued"))
                            : `${t(`imp.stage.${r.stage}`)} · ${fmtInt(r.rows_read)} ${t("app.rows")} · ${Math.round(r.progress)}%`}
                        </span>
                        <button className="text-xs text-bad hover:underline cursor-pointer" onClick={() => cancelImport(r.id)}>{t("app.cancel")}</button>
                      </div>
                      {!waiting && (
                        <div className="h-2.5 bg-surface rounded-full overflow-hidden">
                          <div className="h-full bg-brand transition-all" style={{ width: `${r.progress}%` }} />
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            );
          })()}
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

function DuplicatesCard() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<{ duplicate_lines: number; imports_affected: number } | null>(null);
  const [msg, setMsg] = useState<{ kind: "success" | "danger"; text: string } | null>(null);
  const check = async () => {
    setBusy(true); setMsg(null);
    try { setRes(await api.get("/maintenance/duplicates")); } catch (e) { setMsg({ kind: "danger", text: (e as Error).message }); }
    setBusy(false);
  };
  const remove = async () => {
    if (!confirm(t("imp.dupConfirm"))) return;
    setBusy(true);
    try {
      const r = await api.del("/maintenance/duplicates");
      setMsg({ kind: "success", text: t("imp.dupRemoved", { n: fmtInt(r.removed) }) }); setRes(null);
      qc.invalidateQueries();
    } catch (e) { setMsg({ kind: "danger", text: (e as Error).message }); }
    setBusy(false);
  };
  return (
    <Card title={t("imp.dupTitle")} help={t("imp.dupHelp")}>
      <div className="flex flex-wrap items-center gap-3">
        <button className="btn-ghost" disabled={busy} onClick={check}>{busy && <Loader2 size={16} className="animate-spin" />} {t("imp.dupCheck")}</button>
        {res && (res.duplicate_lines === 0
          ? <span className="text-sm text-good inline-flex items-center gap-1"><CheckCircle2 size={15} /> {t("imp.dupNone")}</span>
          : <>
              <span className="text-sm text-warn font-medium">{t("imp.dupFound", { n: fmtInt(res.duplicate_lines), m: res.imports_affected })}</span>
              <button className="btn-danger" disabled={busy} onClick={remove}><Trash2 size={15} /> {t("imp.dupRemove")}</button>
            </>)}
      </div>
      {msg && <div className="mt-3"><Notice kind={msg.kind}>{msg.text}</Notice></div>}
    </Card>
  );
}
