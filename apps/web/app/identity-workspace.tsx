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

export default function IdentityWorkspace({ apiUrl, token, units, onNotice }: {
  apiUrl: string;
  token: string;
  units: Unit[];
  onNotice: (kind: "success" | "error", text: string) => void;
}) {
  const [users, setUsers] = useState<User[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [issuedLink, setIssuedLink] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    const [userItems, roleItems] = await Promise.all([
      request<User[]>(apiUrl, token, "/api/v1/auth/users"),
      request<Role[]>(apiUrl, token, "/api/v1/auth/roles")
    ]);
    setUsers(userItems);
    setRoles(roleItems);
  }

  useEffect(() => {
    let cancelled = false;
    void Promise.all([
      request<User[]>(apiUrl, token, "/api/v1/auth/users"),
      request<Role[]>(apiUrl, token, "/api/v1/auth/roles")
    ]).then(([userItems, roleItems]) => {
      if (!cancelled) { setUsers(userItems); setRoles(roleItems); }
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
          role_id: values.get("role_id"),
          business_unit_ids: values.getAll("business_unit_ids")
        })
      });
      setIssuedLink(`${window.location.origin}/?access_token=${encodeURIComponent(response.token)}`);
      await load();
      onNotice("success", "Convite seguro criado. Compartilhe o link por um canal confiável.");
    } catch (error) {
      onNotice("error", error instanceof Error ? error.message : "Falha ao convidar");
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
    <header className="contracts-header"><div><p className="overline">IDENTIDADE E AUTORIZAÇÃO</p><h1>Usuários</h1><p>Convites, funções, capacidades e unidades usando a identidade real do STK OS.</p></div><button className="primary new-button" type="button" onClick={() => setInviteOpen(true)}>+ Convidar usuário</button></header>
    {issuedLink && <section className="secure-link"><strong>Link seguro de uso único</strong><code>{issuedLink}</code><button type="button" onClick={() => void navigator.clipboard.writeText(issuedLink)}>Copiar link</button><small>O usuário define a própria senha. O link expira e não pode ser reutilizado.</small></section>}
    <div className="contract-table-shell identity-table"><table className="contract-table"><thead><tr><th>Usuário</th><th>Função</th><th>Escopo</th><th>Primeiro acesso</th><th>Status</th><th>Ações</th></tr></thead><tbody>{users.map((user) => <tr key={user.id}><td data-label="Usuário"><strong>{user.display_name}</strong><span>{user.email}</span></td><td data-label="Função">{user.roles.map((role) => role.name).join(", ")}</td><td data-label="Escopo">{user.business_unit_ids.length ? `${user.business_unit_ids.length} unidade(s)` : "Organização"}</td><td data-label="Primeiro acesso">{user.first_access_completed ? "Concluído" : "Pendente"}</td><td data-label="Status"><span className={`state-pill ${user.status === "active" ? "active" : "terminated"}`}>{user.status === "active" ? "Ativo" : "Desativado"}</span></td><td data-label="Ações"><div className="row-actions"><button type="button" onClick={() => void reset(user)}>Recuperar acesso</button>{user.status === "active" && <button type="button" onClick={() => void deactivate(user)}>Desativar</button>}</div></td></tr>)}</tbody></table></div>
    {inviteOpen && <div className="overlay" role="presentation" onMouseDown={() => setInviteOpen(false)}><section className="panel" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}><header><div><p className="overline">CONVITE SEGURO</p><h2>Novo usuário</h2></div><button type="button" onClick={() => setInviteOpen(false)}>×</button></header><form onSubmit={invite}><label>Nome<input name="display_name" required minLength={2} /></label><label>E-mail<input name="email" type="email" required /></label><label>Função<select name="role_id" required>{roles.map((role) => <option value={role.id} key={role.id}>{role.name}</option>)}</select></label><fieldset><legend>Unidades (nenhuma = organização inteira)</legend><div className="check-list">{units.map((unit) => <label key={unit.id}><input type="checkbox" name="business_unit_ids" value={unit.id} />{unit.name}</label>)}</div></fieldset><p className="form-help">O administrador não cria nem recebe a senha. Será gerado apenas um link temporário para definição pelo próprio usuário.</p><div className="panel-actions"><button type="button" onClick={() => setInviteOpen(false)}>Cancelar</button><button className="primary" disabled={busy} type="submit">{busy ? "Criando…" : "Criar convite"}</button></div></form></section></div>}
  </section>;
}
