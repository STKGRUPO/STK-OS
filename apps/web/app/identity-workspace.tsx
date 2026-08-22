"use client";

import { type FormEvent, useEffect, useState } from "react";

type Role = { id: string; code: string; name: string; capabilities: string[] };
type User = {
  id: string;
  email: string;
  display_name: string;
  status: string;
  first_access_completed: boolean;
  last_login_at: string | null;
  roles: Role[];
  business_unit_ids: string[];
};
type Unit = { id: string; name: string };

async function request<T>(apiUrl: string, token: string, path: string, init?: RequestInit) {
  const response = await fetch(`${apiUrl}${path}`, {
    ...init,
    cache: "no-store",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json", ...init?.headers }
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(payload?.detail ?? `Falha HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

function unitNames(user: User, units: Unit[]) {
  if (user.roles.some((role) => role.code === "administrator")) return "Todas as unidades";
  return user.business_unit_ids
    .map((id) => units.find((unit) => unit.id === id)?.name)
    .filter(Boolean)
    .join(", ") || "Sem unidade";
}

function UnitSelection({ units, selected, onChange, disabled }: {
  units: Unit[];
  selected: string[];
  onChange: (ids: string[]) => void;
  disabled: boolean;
}) {
  return <fieldset disabled={disabled}><legend>{disabled ? "Escopo do perfil" : "Unidades atribuídas"}</legend>
    {disabled ? <p className="form-help">Administrador do Grupo acessa todas as unidades.</p> : <div className="check-list">{units.map((unit) => <label key={unit.id}><input type="checkbox" checked={selected.includes(unit.id)} onChange={() => onChange(selected.includes(unit.id) ? selected.filter((id) => id !== unit.id) : [...selected, unit.id])} />{unit.name}</label>)}</div>}
  </fieldset>;
}

export default function IdentityWorkspace({ apiUrl, token, units, onNotice }: {
  apiUrl: string;
  token: string;
  units: Unit[];
  onNotice: (kind: "success" | "error", text: string) => void;
}) {
  const [users, setUsers] = useState<User[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteRoleId, setInviteRoleId] = useState("");
  const [inviteUnitIds, setInviteUnitIds] = useState<string[]>([]);
  const [editUser, setEditUser] = useState<User | null>(null);
  const [editRoleId, setEditRoleId] = useState("");
  const [editUnitIds, setEditUnitIds] = useState<string[]>([]);
  const [issuedLink, setIssuedLink] = useState("");
  const [busy, setBusy] = useState(false);

  const isGroupAdmin = (roleId: string) => roles.find((role) => role.id === roleId)?.code === "administrator";

  async function load() {
    const [userItems, roleItems] = await Promise.all([
      request<User[]>(apiUrl, token, "/api/v1/auth/users"),
      request<Role[]>(apiUrl, token, "/api/v1/auth/roles")
    ]);
    setUsers(userItems);
    setRoles(roleItems);
    setInviteRoleId((current) => current || roleItems[0]?.id || "");
  }

  useEffect(() => {
    let cancelled = false;
    void Promise.all([
      request<User[]>(apiUrl, token, "/api/v1/auth/users"),
      request<Role[]>(apiUrl, token, "/api/v1/auth/roles")
    ]).then(([userItems, roleItems]) => {
      if (!cancelled) {
        setUsers(userItems);
        setRoles(roleItems);
        setInviteRoleId(roleItems[0]?.id ?? "");
      }
    }).catch((error) => onNotice("error", error instanceof Error ? error.message : "Falha ao carregar usuários"));
    return () => { cancelled = true; };
  }, [apiUrl, token, onNotice]);

  async function invite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    const values = new FormData(event.currentTarget);
    try {
      const response = await request<{ token: string }>(apiUrl, token, "/api/v1/auth/users/invite", {
        method: "POST",
        body: JSON.stringify({
          email: values.get("email"),
          display_name: values.get("display_name"),
          role_id: inviteRoleId,
          business_unit_ids: isGroupAdmin(inviteRoleId) ? [] : inviteUnitIds
        })
      });
      setIssuedLink(`${window.location.origin}/?access_token=${encodeURIComponent(response.token)}`);
      setInviteOpen(false);
      setInviteUnitIds([]);
      await load();
      onNotice("success", "Convite seguro criado. Compartilhe o link por um canal confiável.");
    } catch (error) {
      onNotice("error", error instanceof Error ? error.message : "Falha ao convidar");
    } finally { setBusy(false); }
  }

  function openEdit(user: User) {
    setEditUser(user);
    setEditRoleId(user.roles[0]?.id ?? "");
    setEditUnitIds(user.business_unit_ids);
  }

  async function saveAccess(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editUser) return;
    setBusy(true);
    try {
      await request(apiUrl, token, `/api/v1/auth/users/${editUser.id}/access`, {
        method: "PATCH",
        body: JSON.stringify({
          role_id: editRoleId,
          business_unit_ids: isGroupAdmin(editRoleId) ? [] : editUnitIds
        })
      });
      setEditUser(null);
      await load();
      onNotice("success", "Perfil e unidades atualizados.");
    } catch (error) {
      onNotice("error", error instanceof Error ? error.message : "Falha ao atualizar o acesso");
    } finally { setBusy(false); }
  }

  async function reset(user: User) {
    try {
      const response = await request<{ token: string }>(apiUrl, token, `/api/v1/auth/users/${user.id}/password-reset`, { method: "POST" });
      setIssuedLink(`${window.location.origin}/?access_token=${encodeURIComponent(response.token)}`);
      onNotice("success", "Link de recuperação criado. Nenhuma senha foi enviada.");
    } catch (error) { onNotice("error", error instanceof Error ? error.message : "Falha na recuperação"); }
  }

  async function deactivate(user: User) {
    try {
      await request(apiUrl, token, `/api/v1/auth/users/${user.id}/deactivate`, { method: "PATCH" });
      await load();
      onNotice("success", "Usuário desativado e evento auditado.");
    } catch (error) { onNotice("error", error instanceof Error ? error.message : "Falha ao desativar"); }
  }

  return <section className="workspace identity-workspace">
    <header className="contracts-header"><div><p className="overline">ADMINISTRAÇÃO · IDENTIDADE</p><h1>Usuários</h1><p>Perfis e unidades atribuídas usando o RBAC do STK OS.</p></div><button className="primary new-button" type="button" onClick={() => setInviteOpen(true)}>+ Convidar usuário</button></header>
    {issuedLink && <section className="secure-link"><strong>Link seguro de uso único</strong><code>{issuedLink}</code><button type="button" onClick={() => void navigator.clipboard.writeText(issuedLink)}>Copiar link</button><small>O usuário define a própria senha. O link expira e não pode ser reutilizado.</small></section>}
    <div className="contract-table-shell identity-table"><table className="contract-table"><thead><tr><th>Usuário</th><th>Perfil</th><th>Unidades</th><th>Primeiro acesso</th><th>Status</th><th>Ações</th></tr></thead><tbody>{users.map((user) => <tr key={user.id}><td data-label="Usuário"><strong>{user.display_name}</strong><span>{user.email}</span></td><td data-label="Perfil">{user.roles.map((role) => role.name).join(", ")}</td><td data-label="Unidades">{unitNames(user, units)}</td><td data-label="Primeiro acesso">{user.first_access_completed ? "Concluído" : "Pendente"}</td><td data-label="Status"><span className={`state-pill ${user.status === "active" ? "active" : "terminated"}`}>{user.status === "active" ? "Ativo" : "Desativado"}</span></td><td data-label="Ações"><div className="row-actions"><button type="button" onClick={() => openEdit(user)}>Editar acesso</button><button type="button" onClick={() => void reset(user)}>Recuperar acesso</button>{user.status === "active" && <button type="button" onClick={() => void deactivate(user)}>Desativar</button>}</div></td></tr>)}</tbody></table></div>
    {inviteOpen && <div className="overlay" role="presentation" onMouseDown={() => setInviteOpen(false)}><section className="panel" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}><header><div><p className="overline">CONVITE SEGURO</p><h2>Novo usuário</h2></div><button type="button" onClick={() => setInviteOpen(false)}>×</button></header><form onSubmit={invite}><label>Nome<input name="display_name" required minLength={2} /></label><label>E-mail<input name="email" type="email" required /></label><label>Perfil<select required value={inviteRoleId} onChange={(event) => { setInviteRoleId(event.target.value); setInviteUnitIds([]); }}>{roles.map((role) => <option value={role.id} key={role.id}>{role.name}</option>)}</select></label><UnitSelection units={units} selected={inviteUnitIds} onChange={setInviteUnitIds} disabled={isGroupAdmin(inviteRoleId)} /><p className="form-help">O administrador não cria nem recebe a senha. Será gerado apenas um link temporário para definição pelo próprio usuário.</p><div className="panel-actions"><button type="button" onClick={() => setInviteOpen(false)}>Cancelar</button><button className="primary" disabled={busy} type="submit">{busy ? "Criando…" : "Criar convite"}</button></div></form></section></div>}
    {editUser && <div className="overlay" role="presentation" onMouseDown={() => setEditUser(null)}><section className="panel" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}><header><div><p className="overline">ACESSO DO USUÁRIO</p><h2>{editUser.display_name}</h2><p>{editUser.email}</p></div><button type="button" onClick={() => setEditUser(null)}>×</button></header><form onSubmit={saveAccess}><label>Perfil<select required value={editRoleId} onChange={(event) => { setEditRoleId(event.target.value); setEditUnitIds([]); }}>{roles.map((role) => <option value={role.id} key={role.id}>{role.name}</option>)}</select></label><UnitSelection units={units} selected={editUnitIds} onChange={setEditUnitIds} disabled={isGroupAdmin(editRoleId)} /><div className="panel-actions"><button type="button" onClick={() => setEditUser(null)}>Cancelar</button><button className="primary" disabled={busy} type="submit">{busy ? "Salvando…" : "Salvar acesso"}</button></div></form></section></div>}
  </section>;
}
