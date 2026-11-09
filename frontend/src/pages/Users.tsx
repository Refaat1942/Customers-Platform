import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Lock, Pencil, Plus, Trash2 } from "lucide-react";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useFilters } from "../lib/filters";
import { fmtDate } from "../lib/format";
import DataTable from "../components/DataTable";
import { Badge, Card, ErrorBox, Modal, MultiSelect, Notice, PageHeader, Spinner, Tabs } from "../components/ui";

type Role = { name: string; description: string | null; permissions: string[]; builtin: boolean; users: number };
type Perm = { key: string; en: string; ar: string };
type U = { id: number; username: string; full_name: string | null; role: string; branches: string[]; language: string; active: boolean; created_at?: string };

export default function Users() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<"users" | "roles">("users");
  return (
    <>
      <PageHeader title={t("users.title")} />
      <Tabs value={tab} onChange={setTab} items={[{ key: "users", label: t("users.users") }, { key: "roles", label: t("users.roles") }]} />
      {tab === "users" ? <UsersTab /> : <RolesTab />}
    </>
  );
}

function UsersTab() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const { user: me } = useAuth();
  const users = useQuery({ queryKey: ["users"], queryFn: () => api.get<U[]>("/users") });
  const roles = useQuery({ queryKey: ["roles"], queryFn: () => api.get<{ roles: Role[]; permissions: Perm[] }>("/roles") });
  const [edit, setEdit] = useState<Partial<U> & { password?: string } | null>(null);

  const remove = async (u: U) => {
    if (!confirm(t("users.deleteConfirm"))) return;
    try { await api.del(`/users/${u.id}`); qc.invalidateQueries({ queryKey: ["users"] }); } catch (e) { alert((e as Error).message); }
  };

  if (users.isLoading) return <Spinner />;
  if (users.error) return <ErrorBox error={users.error} />;
  return (
    <Card actions={<button className="btn-primary" onClick={() => setEdit({ role: "manager", branches: [], language: "en", active: true })}><Plus size={16} /> {t("users.newUser")}</button>}>
      <DataTable rows={users.data ?? []} columns={[
        { key: "username", label: t("users.username"), render: (r) => <b>{r.username}</b> },
        { key: "full_name", label: t("users.fullName") },
        { key: "role", label: t("users.role"), render: (r) => <Badge>{r.role}</Badge> },
        { key: "branches", label: t("users.branches"), render: (r) => r.branches.length ? r.branches.join(", ") : <span className="text-muted">{t("users.allBranches")}</span> },
        { key: "language", label: t("users.language"), render: (r) => (r.language === "ar" ? "العربية" : "English") },
        { key: "active", label: t("users.active"), render: (r) => r.active ? <Badge kind="active">{t("app.yes")}</Badge> : <Badge kind="inactive">{t("app.no")}</Badge> },
        { key: "created_at", label: t("audit.time"), render: (r) => fmtDate(r.created_at) },
        { key: "x", label: "", render: (r) => (
          <span className="flex gap-3">
            <button className="text-muted hover:text-ink cursor-pointer" onClick={() => setEdit(r)}><Pencil size={15} /></button>
            {r.id !== me?.id && <button className="text-bad cursor-pointer" onClick={() => remove(r)}><Trash2 size={15} /></button>}
          </span>) },
      ]} />
      {edit && <UserForm initial={edit} roles={roles.data?.roles ?? []} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); qc.invalidateQueries({ queryKey: ["users"] }); }} />}
    </Card>
  );
}

function UserForm({ initial, roles, onClose, onSaved }: { initial: Partial<U> & { password?: string }; roles: Role[]; onClose: () => void; onSaved: () => void }) {
  const { t } = useTranslation();
  const { meta } = useFilters();
  const [u, setU] = useState({ ...initial, password: "" });
  const [err, setErr] = useState<string | null>(null);
  const save = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(null);
    const body = { ...u, password: u.password || null };
    try { u.id ? await api.put(`/users/${u.id}`, body) : await api.post("/users", body); onSaved(); } catch (x) { setErr((x as Error).message); }
  };
  return (
    <Modal title={u.id ? `${t("app.edit")}: ${u.username}` : t("users.newUser")} onClose={onClose}>
      <form onSubmit={save} className="space-y-4">
        <div className="grid sm:grid-cols-2 gap-4">
          <div><label className="label">{t("users.username")}</label><input className="input" required minLength={3} value={u.username ?? ""} onChange={(e) => setU({ ...u, username: e.target.value })} /></div>
          <div><label className="label">{t("users.fullName")}</label><input className="input" value={u.full_name ?? ""} onChange={(e) => setU({ ...u, full_name: e.target.value })} /></div>
          <div><label className="label">{t("users.role")}</label>
            <select className="input" value={u.role} onChange={(e) => setU({ ...u, role: e.target.value })}>
              {roles.map((r) => <option key={r.name} value={r.name}>{r.name}{r.description ? ` — ${r.description}` : ""}</option>)}
            </select></div>
          <div><label className="label">{t("users.language")}</label>
            <select className="input" value={u.language} onChange={(e) => setU({ ...u, language: e.target.value })}>
              <option value="en">English</option><option value="ar">العربية</option>
            </select></div>
        </div>
        <MultiSelect label={`${t("users.branches")} (${t("users.allBranches")} = ${t("app.all")})`} options={meta?.branches ?? []} value={u.branches ?? []} onChange={(v) => setU({ ...u, branches: v })} />
        <div>
          <label className="label">{t("users.password")}</label>
          <input className="input" type="password" autoComplete="new-password" minLength={8} required={!u.id} value={u.password} onChange={(e) => setU({ ...u, password: e.target.value })} />
          <p className="text-xs text-muted mt-1">{t("users.passwordHelp")}</p>
        </div>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="accent-brand" checked={!!u.active} onChange={(e) => setU({ ...u, active: e.target.checked })} /> {t("users.active")}</label>
        {err && <Notice kind="danger">{err}</Notice>}
        <div className="flex gap-2 justify-end"><button type="button" className="btn-ghost" onClick={onClose}>{t("app.cancel")}</button><button className="btn-primary">{t("app.save")}</button></div>
      </form>
    </Modal>
  );
}

function RolesTab() {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["roles"], queryFn: () => api.get<{ roles: Role[]; permissions: Perm[] }>("/roles") });
  const [draft, setDraft] = useState<Record<string, string[]>>({});
  const [newRole, setNewRole] = useState<{ name: string; description: string } | null>(null);
  const [msg, setMsg] = useState<{ kind: "success" | "danger"; text: string } | null>(null);

  if (q.isLoading) return <Spinner />;
  if (q.error || !q.data) return <ErrorBox error={q.error} />;
  const { roles, permissions } = q.data;
  const permsOf = (r: Role) => draft[r.name] ?? r.permissions;
  const toggle = (r: Role, p: string) => {
    const cur = permsOf(r);
    setDraft({ ...draft, [r.name]: cur.includes(p) ? cur.filter((x) => x !== p) : [...cur, p] });
  };
  const dirty = Object.keys(draft);

  const save = async () => {
    setMsg(null);
    try {
      for (const name of dirty) {
        const r = roles.find((x) => x.name === name)!;
        await api.put(`/roles/${name}`, { name, description: r.description, permissions: draft[name] });
      }
      setDraft({}); setMsg({ kind: "success", text: t("app.saved") });
      qc.invalidateQueries({ queryKey: ["roles"] });
    } catch (e) { setMsg({ kind: "danger", text: (e as Error).message }); }
  };
  const create = async () => {
    if (!newRole) return;
    try { await api.post("/roles", { ...newRole, permissions: ["dashboard"] }); setNewRole(null); qc.invalidateQueries({ queryKey: ["roles"] }); }
    catch (e) { setMsg({ kind: "danger", text: (e as Error).message }); }
  };
  const remove = async (name: string) => {
    if (!confirm(t("users.deleteRoleConfirm"))) return;
    try { await api.del(`/roles/${name}`); qc.invalidateQueries({ queryKey: ["roles"] }); } catch (e) { setMsg({ kind: "danger", text: (e as Error).message }); }
  };

  return (
    <Card actions={<>
      <button className="btn-ghost" onClick={() => setNewRole({ name: "", description: "" })}><Plus size={16} /> {t("users.newRole")}</button>
      <button className="btn-primary" disabled={!dirty.length} onClick={save}>{t("app.save")}{dirty.length ? ` (${dirty.length})` : ""}</button>
    </>}>
      {msg && <div className="mb-3"><Notice kind={msg.kind}>{msg.text}</Notice></div>}
      <div className="overflow-auto border border-line rounded-lg">
        <table className="w-full border-collapse text-sm">
          <thead className="bg-surface">
            <tr>
              <th className="th">{t("users.permission")}</th>
              {roles.map((r) => (
                <th key={r.name} className="th text-center">
                  <div className="flex items-center justify-center gap-1">
                    {r.builtin && <Lock size={12} />} {r.name}
                    {!r.builtin && r.users === 0 && <button className="text-bad ms-1 cursor-pointer" onClick={() => remove(r.name)}><Trash2 size={12} /></button>}
                  </div>
                  <div className="font-normal text-[11px]">{r.users} {t("users.usersCount")}</div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {permissions.map((p) => (
              <tr key={p.key} className="border-t border-line hover:bg-surface/60">
                <td className="td">{i18n.language === "ar" ? p.ar : p.en}</td>
                {roles.map((r) => (
                  <td key={r.name} className="td text-center">
                    <input type="checkbox" className="accent-brand size-4 cursor-pointer disabled:cursor-not-allowed"
                      disabled={r.name === "admin"} checked={permsOf(r).includes(p.key)} onChange={() => toggle(r, p.key)}
                      title={r.name === "admin" ? t("users.builtinAdmin") : undefined} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted mt-2">{t("users.builtinAdmin")}</p>
      {newRole && (
        <Modal title={t("users.newRole")} onClose={() => setNewRole(null)}>
          <div className="space-y-4">
            <div><label className="label">{t("users.roleName")}</label><input className="input" pattern="[a-z0-9_]+" value={newRole.name} onChange={(e) => setNewRole({ ...newRole, name: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_") })} /></div>
            <div><label className="label">{t("users.description")}</label><input className="input" value={newRole.description} onChange={(e) => setNewRole({ ...newRole, description: e.target.value })} /></div>
            <div className="flex justify-end gap-2"><button className="btn-ghost" onClick={() => setNewRole(null)}>{t("app.cancel")}</button><button className="btn-primary" disabled={newRole.name.length < 2} onClick={create}>{t("app.add")}</button></div>
          </div>
        </Modal>
      )}
    </Card>
  );
}
