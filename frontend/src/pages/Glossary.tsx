import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useLocation } from "react-router-dom";
import clsx from "clsx";
import { Search } from "lucide-react";
import { GROUPS, TERMS } from "../glossary";
import { PageHeader } from "../components/ui";

export default function Glossary() {
  const { t, i18n } = useTranslation();
  const loc = useLocation();
  const [q, setQ] = useState("");
  const idx = i18n.language === "ar" ? 3 : 2;
  const target = loc.hash.replace("#", "");

  useEffect(() => {
    if (!target) return;
    setTimeout(() => document.getElementById(`term-${target}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 100);
  }, [target]);

  const match = (e: (typeof TERMS)[number]) => {
    if (!q.trim()) return true;
    const s = q.trim().toLowerCase();
    return [...e[2], ...e[3]].some((x) => x.toLowerCase().includes(s));
  };

  return (
    <>
      <PageHeader title={t("glossary.title")} subtitle={t("glossary.subtitle")} />
      <div className="relative mb-5 max-w-xl">
        <Search size={17} className="absolute top-3 start-3 text-muted" />
        <input autoFocus className="input ps-10 py-2.5" placeholder={t("glossary.search")} value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <div className="space-y-6">
        {GROUPS.map((g) => {
          const items = TERMS.filter((e) => e[1] === g && match(e));
          if (!items.length) return null;
          return (
            <section key={g}>
              <h2 className="text-sm font-semibold uppercase tracking-wider text-muted mb-3">{t(`glossary.groups.${g}`)}</h2>
              <div className="grid md:grid-cols-2 gap-3">
                {items.map((e) => {
                  const [name, short, long] = e[idx];
                  return (
                    <div key={e[0]} id={`term-${e[0]}`}
                      className={clsx("card p-4 scroll-mt-24 transition", target === e[0] && "ring-2 ring-brand")}>
                      <div className="font-semibold">{name}</div>
                      <div className="text-sm mt-1">{short}</div>
                      {long && <div className="text-sm text-muted mt-2 leading-relaxed">{long}</div>}
                    </div>
                  );
                })}
              </div>
            </section>
          );
        })}
      </div>
    </>
  );
}
