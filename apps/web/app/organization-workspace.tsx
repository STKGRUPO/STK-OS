"use client";

import { type FormEvent, useEffect, useState } from "react";

type Unit = { id: string; name: string };
type BusinessUnit = Unit & { code: string; status: string; primary_establishment_id: string };
type Establishment = {
  id: string;
  code: string;
  name: string;
  kind: "headquarters" | "branch";
  tax_id: string | null;
  status: "active" | "inactive";
  legal_entity_id: string;
  business_units: BusinessUnit[];
};
type LegalEntity = {
  id: string;
  code: string;
  registered_name: string;
  trade_name: string | null;
  tax_id: string | null;
  status: "active" | "inactive";
  establishments: Establishment[];
};
type Organization = { id: string; name: string; legal_entities: LegalEntity[] };

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

function cnpj(value: string | null) {
  if (!value) return "Não informado";
  return value.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, "$1.$2.$3/$4-$5");
}

export default function OrganizationWorkspace({ apiUrl, token, units, canWrite, onNotice }: {
  apiUrl: string;
  token: string;
  units: Unit[];
  canWrite: boolean;
  onNotice: (kind: "success" | "error", text: string) => void;
}) {
  const [organization, setOrganization] = useState<Organization | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [entityForm, setEntityForm] = useState<LegalEntity | "new" | null>(null);
  const [establishmentForm, setEstablishmentForm] = useState<Establishment | "new" | null>(null);
  const [establishmentUnitIds, setEstablishmentUnitIds] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  const selected = organization?.legal_entities.find((item) => item.id === selectedId) ?? null;

  async function load(preferredEntityId?: string) {
    const payload = await request<Organization>(apiUrl, token, "/api/v1/organization");
    setOrganization(payload);
    if (preferredEntityId) setSelectedId(preferredEntityId);
  }

  useEffect(() => {
    let cancelled = false;
    void request<Organization>(apiUrl, token, "/api/v1/organization").then((payload) => {
      if (!cancelled) setOrganization(payload);
    }).catch((error) => onNotice("error", error instanceof Error ? error.message : "Falha ao carregar empresas"));
    return () => { cancelled = true; };
  }, [apiUrl, token, onNotice]);

  async function saveEntity(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!entityForm) return;
    setBusy(true);
    const values = new FormData(event.currentTarget);
    const body = {
      registered_name: values.get("registered_name"),
      trade_name: values.get("trade_name") || null,
      tax_id: values.get("tax_id") || null,
      status: values.get("status")
    };
    try {
      const creating = entityForm === "new";
      const entity = await request<LegalEntity>(apiUrl, token, creating ? "/api/v1/organization/legal-entities" : `/api/v1/organization/legal-entities/${entityForm.id}`, {
        method: creating ? "POST" : "PATCH",
        body: JSON.stringify(body)
      });
      setEntityForm(null);
      await load(entity.id);
      onNotice("success", creating ? "Empresa do Grupo cadastrada." : "Empresa do Grupo atualizada.");
    } catch (error) {
      onNotice("error", error instanceof Error ? error.message : "Falha ao salvar empresa");
    } finally { setBusy(false); }
  }

  async function toggleEntity(entity: LegalEntity) {
    try {
      await request(apiUrl, token, `/api/v1/organization/legal-entities/${entity.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          registered_name: entity.registered_name,
          trade_name: entity.trade_name,
          tax_id: entity.tax_id,
          status: entity.status === "active" ? "inactive" : "active"
        })
      });
      await load(entity.id);
      onNotice("success", entity.status === "active" ? "Empresa desativada." : "Empresa ativada.");
    } catch (error) { onNotice("error", error instanceof Error ? error.message : "Falha ao alterar status"); }
  }

  function openEstablishmentForm(value: Establishment | "new") {
    setEstablishmentForm(value);
    setEstablishmentUnitIds(value === "new" ? [] : value.business_units.map((unit) => unit.id));
  }

  async function saveEstablishment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected || !establishmentForm) return;
    setBusy(true);
    const values = new FormData(event.currentTarget);
    const body = {
      name: values.get("name"),
      tax_id: values.get("tax_id") || null,
      kind: values.get("kind"),
      status: values.get("status"),
      business_unit_ids: establishmentUnitIds
    };
    try {
      const creating = establishmentForm === "new";
      await request(apiUrl, token, creating ? `/api/v1/organization/legal-entities/${selected.id}/fiscal-establishments` : `/api/v1/organization/fiscal-establishments/${establishmentForm.id}`, {
        method: creating ? "POST" : "PATCH",
        body: JSON.stringify(body)
      });
      setEstablishmentForm(null);
      await load(selected.id);
      onNotice("success", creating ? "Estabelecimento fiscal cadastrado." : "Estabelecimento fiscal atualizado.");
    } catch (error) {
      onNotice("error", error instanceof Error ? error.message : "Falha ao salvar estabelecimento");
    } finally { setBusy(false); }
  }

  async function toggleEstablishment(establishment: Establishment) {
    try {
      await request(apiUrl, token, `/api/v1/organization/fiscal-establishments/${establishment.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: establishment.name,
          tax_id: establishment.tax_id,
          kind: establishment.kind,
          status: establishment.status === "active" ? "inactive" : "active",
          business_unit_ids: establishment.business_units.map((unit) => unit.id)
        })
      });
      await load(selected?.id);
      onNotice("success", establishment.status === "active" ? "Estabelecimento desativado." : "Estabelecimento ativado.");
    } catch (error) { onNotice("error", error instanceof Error ? error.message : "Falha ao alterar status"); }
  }

  return <section className="workspace organization-workspace">
    <header className="contracts-header"><div><p className="overline">ADMINISTRAÇÃO · ESTRUTURA JURÍDICA</p><h1>Empresas do Grupo</h1><p>Pessoas jurídicas do Grupo, seus estabelecimentos fiscais e vínculos com unidades de negócio.</p></div>{canWrite && <button className="primary new-button" type="button" onClick={() => setEntityForm("new")}>+ Nova empresa</button>}</header>
    <section className="structure-note"><strong>Estrutura preservada</strong><span>Grupo → Pessoa Jurídica → Estabelecimento Fiscal → Unidade de Negócio</span><small>MR, STK Lab e Stelli permanecem unidades comerciais; CNPJs e estabelecimentos formam a estrutura jurídica e fiscal.</small></section>
    <div className="contract-table-shell organization-table"><table className="contract-table"><thead><tr><th>Empresa do Grupo</th><th>CNPJ</th><th>Estabelecimentos</th><th>Unidades vinculadas</th><th>Status</th><th>Ações</th></tr></thead><tbody>{organization?.legal_entities.map((entity) => { const linkedUnits = new Set(entity.establishments.flatMap((item) => item.business_units.map((unit) => unit.id))); return <tr key={entity.id}><td data-label="Empresa"><strong>{entity.trade_name || entity.registered_name}</strong><span>{entity.registered_name}</span></td><td data-label="CNPJ">{cnpj(entity.tax_id)}</td><td data-label="Estabelecimentos">{entity.establishments.length}</td><td data-label="Unidades">{linkedUnits.size}</td><td data-label="Status"><span className={`state-pill ${entity.status === "active" ? "active" : "terminated"}`}>{entity.status === "active" ? "Ativa" : "Inativa"}</span></td><td data-label="Ações"><div className="row-actions"><button type="button" onClick={() => setSelectedId(entity.id)}>Abrir</button>{canWrite && <><button type="button" onClick={() => setEntityForm(entity)}>Editar</button><button type="button" onClick={() => void toggleEntity(entity)}>{entity.status === "active" ? "Desativar" : "Ativar"}</button></>}</div></td></tr>; })}</tbody></table></div>
    {selected && <div className="overlay" role="presentation" onMouseDown={() => setSelectedId(null)}><section className="drawer organization-drawer" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}><header><div><p className="overline">PESSOA JURÍDICA</p><h2>{selected.trade_name || selected.registered_name}</h2><p>{selected.registered_name} · {cnpj(selected.tax_id)}</p></div><button type="button" onClick={() => setSelectedId(null)}>×</button></header><div className="organization-detail"><div className="detail-actions">{canWrite && <><button type="button" onClick={() => setEntityForm(selected)}>Editar empresa</button><button className="primary" type="button" onClick={() => openEstablishmentForm("new")}>+ Estabelecimento fiscal</button></>}</div><h3>Estabelecimentos fiscais</h3>{selected.establishments.length ? <div className="establishment-list">{selected.establishments.map((item) => <article key={item.id}><div><span className="overline">{item.kind === "headquarters" ? "MATRIZ" : "FILIAL"}</span><strong>{item.name}</strong><small>{cnpj(item.tax_id)} · {item.status === "active" ? "Ativo" : "Inativo"}</small><p>{item.business_units.length ? `Unidades: ${item.business_units.map((unit) => unit.name).join(", ")}` : "Nenhuma unidade vinculada"}</p></div>{canWrite && <div className="row-actions"><button type="button" onClick={() => openEstablishmentForm(item)}>Editar</button><button type="button" onClick={() => void toggleEstablishment(item)}>{item.status === "active" ? "Desativar" : "Ativar"}</button></div>}</article>)}</div> : <p className="empty-state">Nenhum estabelecimento fiscal cadastrado.</p>}<p className="form-help">A configuração fiscal e a referência segura ao certificado poderão ser associadas a cada estabelecimento pelo modelo fiscal já existente.</p></div></section></div>}
    {entityForm && <div className="overlay" role="presentation" onMouseDown={() => setEntityForm(null)}><section className="panel" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}><header><div><p className="overline">EMPRESA DO GRUPO</p><h2>{entityForm === "new" ? "Nova pessoa jurídica" : "Editar pessoa jurídica"}</h2></div><button type="button" onClick={() => setEntityForm(null)}>×</button></header><form onSubmit={saveEntity}><label>Razão social<input name="registered_name" required minLength={2} defaultValue={entityForm === "new" ? "" : entityForm.registered_name} /></label><label>Nome fantasia<input name="trade_name" defaultValue={entityForm === "new" ? "" : entityForm.trade_name ?? ""} /></label><label>CNPJ<input name="tax_id" inputMode="numeric" placeholder="00.000.000/0000-00" defaultValue={entityForm === "new" ? "" : cnpj(entityForm.tax_id)} /></label><label>Status<select name="status" defaultValue={entityForm === "new" ? "active" : entityForm.status}><option value="active">Ativa</option><option value="inactive">Inativa</option></select></label><div className="panel-actions"><button type="button" onClick={() => setEntityForm(null)}>Cancelar</button><button className="primary" disabled={busy} type="submit">{busy ? "Salvando…" : "Salvar empresa"}</button></div></form></section></div>}
    {establishmentForm && selected && <div className="overlay" role="presentation" onMouseDown={() => setEstablishmentForm(null)}><section className="panel" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}><header><div><p className="overline">ESTABELECIMENTO FISCAL</p><h2>{establishmentForm === "new" ? "Novo estabelecimento" : "Editar estabelecimento"}</h2><p>{selected.trade_name || selected.registered_name}</p></div><button type="button" onClick={() => setEstablishmentForm(null)}>×</button></header><form onSubmit={saveEstablishment}><label>Nome<input name="name" required minLength={2} defaultValue={establishmentForm === "new" ? "" : establishmentForm.name} /></label><label>CNPJ do emissor<input name="tax_id" inputMode="numeric" placeholder="00.000.000/0000-00" defaultValue={establishmentForm === "new" ? "" : cnpj(establishmentForm.tax_id)} /></label><div className="form-grid"><label>Tipo<select name="kind" defaultValue={establishmentForm === "new" ? "headquarters" : establishmentForm.kind}><option value="headquarters">Matriz</option><option value="branch">Filial</option></select></label><label>Status<select name="status" defaultValue={establishmentForm === "new" ? "active" : establishmentForm.status}><option value="active">Ativo</option><option value="inactive">Inativo</option></select></label></div><fieldset><legend>Unidades de negócio vinculadas</legend><div className="check-list">{units.map((unit) => <label key={unit.id}><input type="checkbox" checked={establishmentUnitIds.includes(unit.id)} onChange={() => setEstablishmentUnitIds((current) => current.includes(unit.id) ? current.filter((id) => id !== unit.id) : [...current, unit.id])} />{unit.name}</label>)}</div></fieldset><p className="form-help">Selecionar uma unidade a move para este estabelecimento. Para remover um vínculo, vincule a unidade ao estabelecimento de destino.</p><div className="panel-actions"><button type="button" onClick={() => setEstablishmentForm(null)}>Cancelar</button><button className="primary" disabled={busy} type="submit">{busy ? "Salvando…" : "Salvar estabelecimento"}</button></div></form></section></div>}
  </section>;
}
