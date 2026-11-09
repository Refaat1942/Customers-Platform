import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Bot, Copy, FileText, Loader2, RotateCcw, Send, User } from "lucide-react";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useFilters } from "../lib/filters";
import FilterBar from "../components/FilterBar";
import { Notice, PageHeader, PrintButton } from "../components/ui";

type Msg = { role: "user" | "assistant"; content: string; error?: boolean };

export default function AIAnalyst() {
  const { t, i18n } = useTranslation();
  const { params, meta } = useFilters();
  const { can } = useAuth();
  const [msgs, setMsgs] = useState<Msg[]>(() => {
    try { return JSON.parse(sessionStorage.getItem("ai_chat") || "[]"); } catch { return []; }
  });
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    try { sessionStorage.setItem("ai_chat", JSON.stringify(msgs)); } catch { /* */ }
    end.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs]);

  const send = async (question: string, report = false) => {
    if (busy || (!report && !question.trim())) return;
    const history = msgs.filter((m) => !m.error);
    const userMsg: Msg = { role: "user", content: report ? t("ai.report") : question };
    setMsgs((m) => [...m, userMsg]); setText(""); setBusy(true);
    try {
      const qs = new URLSearchParams();
      Object.entries(params).forEach(([k, v]) => Array.isArray(v) ? v.forEach((x) => qs.append(k, x)) : v && qs.append(k, String(v)));
      const r = await api.post(`/ai/ask?${qs}`, { question, history, report, lang: i18n.language });
      setMsgs((m) => [...m, { role: "assistant", content: r.answer }]);
    } catch (e) {
      setMsgs((m) => [...m, { role: "assistant", content: (e as Error).message, error: true }]);
    }
    setBusy(false);
  };

  const suggestions = t("ai.suggestions", { returnObjects: true }) as string[];

  return (
    <>
      <PageHeader title={t("ai.title")} subtitle={t("ai.subtitle")}
        actions={<>
          <button className="btn-primary" disabled={busy || !meta?.ai_enabled} onClick={() => send("", true)}><FileText size={16} /> {t("ai.report")}</button>
          {msgs.length > 0 && <><PrintButton /><button className="btn-ghost" onClick={() => setMsgs([])}><RotateCcw size={16} /> {t("ai.clear")}</button></>}
        </>} />
      <FilterBar />
      {meta && !meta.ai_enabled && (
        <div className="mb-5"><Notice kind="warning">{t("ai.noKey")} {can("settings") && <Link className="underline font-semibold" to="/settings">{t("nav.settings")}</Link>}</Notice></div>
      )}
      <div className="card flex flex-col min-h-[60vh]">
        <div className="flex-1 p-5 space-y-5">
          {msgs.length === 0 && (
            <div className="grid sm:grid-cols-2 gap-3 max-w-3xl mx-auto pt-6">
              {suggestions.map((s) => (
                <button key={s} disabled={!meta?.ai_enabled} onClick={() => send(s)}
                  className="text-start text-sm rounded-lg border border-line p-4 hover:border-brand hover:bg-brand-soft transition cursor-pointer disabled:opacity-50">{s}</button>
              ))}
            </div>
          )}
          {msgs.map((m, i) => (
            <div key={i} className="flex gap-3 max-w-4xl">
              <div className={`size-8 shrink-0 rounded-full grid place-items-center ${m.role === "user" ? "bg-surface" : "bg-brand text-white"}`}>
                {m.role === "user" ? <User size={16} /> : <Bot size={16} />}
              </div>
              <div className="flex-1 min-w-0">
                {m.role === "user" ? <div className="font-medium pt-1">{m.content}</div>
                  : m.error ? <Notice kind="danger">{m.content}</Notice>
                  : <div className="prose-ai text-sm overflow-x-auto">
                      <Markdown remarkPlugins={[remarkGfm]}>{m.content}</Markdown>
                      <button className="text-xs text-muted hover:text-ink inline-flex items-center gap-1 mt-1 no-print cursor-pointer"
                        onClick={() => navigator.clipboard?.writeText(m.content)}><Copy size={12} /> {t("ai.copy")}</button>
                    </div>}
              </div>
            </div>
          ))}
          {busy && <div className="flex items-center gap-2 text-sm text-muted"><Loader2 size={16} className="animate-spin" /> {t("ai.thinking")}</div>}
          <div ref={end} />
        </div>
        <form className="border-t border-line p-3 flex gap-2 no-print" onSubmit={(e) => { e.preventDefault(); send(text); }}>
          <input className="input" placeholder={t("ai.placeholder")} value={text} onChange={(e) => setText(e.target.value)} disabled={!meta?.ai_enabled} />
          <button className="btn-primary" disabled={busy || !text.trim()}><Send size={16} className="rtl:-scale-x-100" /> {t("ai.ask")}</button>
        </form>
      </div>
    </>
  );
}
