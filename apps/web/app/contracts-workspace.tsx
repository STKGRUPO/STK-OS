"use client";

import { type FormEvent, useEffect, useMemo, useState } from "react";

type RefItem = {
  id: string;
  name: string;
  business_unit_id?: string | null;
  company_id?: string | null;
  kind?: string | null;
  value?: string | null;
};
type ContractReference = {
  business_units: RefItem[];
  companies: RefItem[];
  fiscal_establishments: RefItem[];
  products_services: RefItem[];
  contact_methods: RefItem[];
};
type ContractSummary = {
  id: string;
  business_unit_id: string;
  business_unit_name: string;
  customer_company_id: string;
  customer_name: string;
  internal_number: string;
  administrative_status: string;
  signed_on: string | null;
  start_date: string;
  contract_type: string;
  current_operational_state: "active" | "suspended" | "terminated";
  current_version_number: number | null;
  current_issuer_establishment_id: string | null;
  current_issuer_name: string | null;
  current_amount: string | null;
  current_currency: string | null;
  scheduled_versions: number;
};
type Service = {
  id: string;
  product_service_id: string | null;
  product_name: string | null;
  contractual_description: string;
  quantity: string;
  unit_amount: string | null;
  is_active: boolean;
};
type FinancialContact = {
  id: string;
  contact_method_id: string;
  contact_name: string;
  contact_value: string;
  recipient_role: string;
  purpose: string;
  preferred_channel: string;
};
type Version = {
  id: string;
  version_number: number;
  effective_from: string;
  effective_until: string | null;
  temporal_status: "historical" | "current" | "scheduled";
  issuer_establishment_id: string;
  issuer_name: string;
  currency: string;
  billing_frequency: string;
  pricing_model: string;
  amount: string;
  billing_installments: number | null;
  billing_day: number | null;
  payment_terms_days: number | null;
  invoice_description: string | null;
  adjustment_reference: string | null;
  adjustment_frequency: string | null;
  adjustment_base_date: string | null;
  adjustment_applied_percentage: string | null;
  adjustment_source: string | null;
  change_type: string;
  change_reason: string;
  configuration_sha256: string;
  services: Service[];
  financial_contacts: FinancialContact[];
};
type OperationalEvent = {
  id: string;
  event_type: string;
  effective_on: string;
  reason: string;
};
type ContractDetail = ContractSummary & {
  controlled_notes: string | null;
  versions: Version[];
  operational_events: OperationalEvent[];
};
type Modal = "contract" | "version" | "operation" | null;
type Notice = (kind: "success" | "error", text: string) => void;

async function request<T>(
  apiUrl: string,
  token: string,
  path: string,
  init?: RequestInit,
  command = false
): Promise<T> {
  const response = await fetch(`${apiUrl}${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      ...(command ? { "Idempotency-Key": crypto.randomUUID() } : {}),
      ...init?.headers
    }
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(payload?.detail ?? `Falha HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

function brl(value: string | null, currency = "BRL") {
  if (value === null) return "Sem versão publicada";
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency }).format(Number(value));
}

function dateLabel(value: string | null) {
  if (!value) return "em aberto";
  return new Intl.DateTimeFormat("pt-BR", { timeZone: "UTC" }).format(new Date(`${value}T00:00:00Z`));
}

function isoToday() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

function nextDay(value: string) {
  const date = new Date(`${value}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + 1);
  return date.toISOString().slice(0, 10);
}

function operationalLabel(value: string) {
  return ({
    active: "Ativo",
    suspended: "Suspenso",
    terminated: "Encerrado"
  } as Record<string, string>)[value] ?? value;
}

function eventLabel(value: string) {
  return ({
    suspended: "Suspensão",
    resumed: "Retomada",
    terminated: "Encerramento",
    renewed: "Renovação"
  } as Record<string, string>)[value] ?? value;
}

function versionDiff(current: Version, previous?: Version) {
  if (!previous) return ["Configuração inicial publicada"];
  const changes: string[] = [];
  if (current.amount !== previous.amount) changes.push(`Valor: ${brl(previous.amount)} → ${brl(current.amount)}`);
  if (current.issuer_establishment_id !== previous.issuer_establishment_id) {
    changes.push(`Emissor: ${previous.issuer_name} → ${current.issuer_name}`);
  }
  if (current.billing_frequency !== previous.billing_frequency) changes.push("Periodicidade alterada");
  const active = new Set(current.services.filter((item) => item.is_active).map((item) => item.contractual_description));
  const previousActive = new Set(previous.services.filter((item) => item.is_active).map((item) => item.contractual_description));
  for (const service of active) if (!previousActive.has(service)) changes.push(`Serviço incluído: ${service}`);
  for (const service of previousActive) if (!active.has(service)) changes.push(`Serviço excluído: ${service}`);
  return changes.length ? changes : ["Condições e metadados contratuais alterados"];
}

export default function ContractsWorkspace({
  apiUrl,
  token,
  onNotice
}: {
  apiUrl: string;
  token: string;
  onNotice: Notice;
}) {
  const [reference, setReference] = useState<ContractReference | null>(null);
  const [contracts, setContracts] = useState<ContractSummary[]>([]);
  const [selected, setSelected] = useState<ContractDetail | null>(null);
  const [modal, setModal] = useState<Modal>(null);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ unit: "", customer: "", status: "", issuer: "", validOn: "" });

  useEffect(() => {
    let active = true;
    async function initialLoad() {
      try {
        const [refs, items] = await Promise.all([
          request<ContractReference>(apiUrl, token, "/api/v1/contracts/reference-data"),
          request<ContractSummary[]>(apiUrl, token, "/api/v1/contracts")
        ]);
        if (active) {
          setReference(refs);
          setContracts(items);
        }
      } catch (error) {
        if (active) onNotice("error", error instanceof Error ? error.message : "Falha ao abrir contratos");
      } finally {
        if (active) setLoading(false);
      }
    }
    void initialLoad();
    return () => { active = false; };
  }, [apiUrl, token, onNotice]);

  async function loadContracts() {
    setLoading(true);
    const params = new URLSearchParams();
    if (filters.unit) params.set("business_unit_id", filters.unit);
    if (filters.customer) params.set("customer_company_id", filters.customer);
    if (filters.status) params.set("administrative_status", filters.status);
    if (filters.issuer) params.set("issuer_establishment_id", filters.issuer);
    if (filters.validOn) params.set("valid_on", filters.validOn);
    try {
      setContracts(await request<ContractSummary[]>(apiUrl, token, `/api/v1/contracts?${params}`));
    } catch (error) {
      onNotice("error", error instanceof Error ? error.message : "Falha ao filtrar contratos");
    } finally {
      setLoading(false);
    }
  }

  async function openContract(id: string) {
    try {
      setSelected(await request<ContractDetail>(apiUrl, token, `/api/v1/contracts/${id}`));
    } catch (error) {
      onNotice("error", error instanceof Error ? error.message : "Falha ao consultar contrato");
    }
  }

  async function refresh(message: string, contractId?: string) {
    await loadContracts();
    if (contractId) await openContract(contractId);
    setModal(null);
    onNotice("success", message);
  }

  const currentCount = contracts.filter((item) => item.current_version_number !== null).length;
  const scheduledCount = contracts.reduce((total, item) => total + item.scheduled_versions, 0);
  const suspendedCount = contracts.filter((item) => item.current_operational_state === "suspended").length;

  return (
    <section className="workspace contracts-workspace">
      <header className="contracts-header">
        <div><p className="overline">DOMÍNIO CONTRATUAL · ETAPA 4</p><h1>Contratos versionados</h1><p>Condições históricas preservadas por vigência.</p></div>
        <button className="primary new-button" type="button" onClick={() => setModal("contract")}>+ Novo contrato</button>
      </header>
      <form className="contract-filters" onSubmit={(event) => { event.preventDefault(); void loadContracts(); }}>
        <label>Unidade<select value={filters.unit} onChange={(event) => setFilters({ ...filters, unit: event.target.value })}><option value="">Todas</option>{reference?.business_units.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
        <label>Cliente<select value={filters.customer} onChange={(event) => setFilters({ ...filters, customer: event.target.value })}><option value="">Todos</option>{reference?.companies.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
        <label>Status<select value={filters.status} onChange={(event) => setFilters({ ...filters, status: event.target.value })}><option value="">Todos</option><option value="draft">Rascunho</option><option value="active">Ativo administrativo</option><option value="archived">Arquivado</option></select></label>
        <label>Emissor<select value={filters.issuer} onChange={(event) => setFilters({ ...filters, issuer: event.target.value })}><option value="">Todos</option>{reference?.fiscal_establishments.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
        <label>Vigente em<input type="date" value={filters.validOn} onChange={(event) => setFilters({ ...filters, validOn: event.target.value })} /></label>
        <button type="submit">Aplicar filtros</button>
      </form>
      <section className="metrics contract-metrics"><article><span>COM VERSÃO VIGENTE</span><strong>{currentCount}</strong><small>configuração consultável</small></article><article><span>VERSÕES FUTURAS</span><strong>{scheduledCount}</strong><small>alterações programadas</small></article><article className={suspendedCount ? "attention" : ""}><span>SUSPENSOS</span><strong>{suspendedCount}</strong><small>estado operacional</small></article></section>
      <section className={`contract-table-shell ${loading ? "loading" : ""}`}>
        <table className="contract-table"><thead><tr><th>Contrato / cliente</th><th>Unidade</th><th>Vigência</th><th>Emissor atual</th><th>Valor</th><th>Situação</th><th /></tr></thead><tbody>
          {contracts.map((item) => <tr key={item.id}><td data-label="Contrato / cliente"><strong>{item.internal_number}</strong><span>{item.customer_name}</span></td><td data-label="Unidade">{item.business_unit_name}</td><td data-label="Vigência">desde {dateLabel(item.start_date)}<small>v{item.current_version_number ?? "—"} · {item.scheduled_versions} futura(s)</small></td><td data-label="Emissor atual">{item.current_issuer_name ?? "Aguardando versão"}</td><td data-label="Valor">{brl(item.current_amount, item.current_currency ?? "BRL")}</td><td data-label="Situação"><span className={`state-pill ${item.current_operational_state}`}>{operationalLabel(item.current_operational_state)}</span></td><td><button type="button" onClick={() => void openContract(item.id)}>Abrir contrato →</button></td></tr>)}
          {!contracts.length && <tr><td className="contract-empty" colSpan={7}>Nenhum contrato corresponde aos filtros.</td></tr>}
        </tbody></table>
      </section>
      {selected && <ContractDrawer detail={selected} apiUrl={apiUrl} token={token} onClose={() => setSelected(null)} onVersion={() => setModal("version")} onOperation={() => setModal("operation")} onNotice={onNotice} />}
      {modal === "contract" && reference && <ContractCreateModal reference={reference} apiUrl={apiUrl} token={token} onClose={() => setModal(null)} onDone={(message, id) => refresh(message, id)} onNotice={onNotice} />}
      {modal === "version" && reference && selected && <VersionModal reference={reference} detail={selected} apiUrl={apiUrl} token={token} onClose={() => setModal(null)} onDone={(message) => refresh(message, selected.id)} onNotice={onNotice} />}
      {modal === "operation" && selected && <OperationModal detail={selected} apiUrl={apiUrl} token={token} onClose={() => setModal(null)} onDone={(message) => refresh(message, selected.id)} onNotice={onNotice} />}
    </section>
  );
}

function ContractCreateModal({ reference, apiUrl, token, onClose, onDone, onNotice }: { reference: ContractReference; apiUrl: string; token: string; onClose: () => void; onDone: (message: string, id: string) => Promise<void>; onNotice: Notice }) {
  const [busy, setBusy] = useState(false);
  const [unit, setUnit] = useState(reference.business_units[0]?.id ?? "");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); const data = new FormData(event.currentTarget);
    try {
      const result = await request<ContractSummary>(apiUrl, token, "/api/v1/contracts", { method: "POST", body: JSON.stringify({ business_unit_id: unit, customer_company_id: data.get("customer"), internal_number: data.get("number"), signed_on: data.get("signed_on") || null, start_date: data.get("start_date"), contract_type: data.get("type"), controlled_notes: data.get("notes") || null }) }, true);
      await onDone("Contrato criado. Publique agora sua primeira versão.", result.id);
    } catch (error) { onNotice("error", error instanceof Error ? error.message : "Falha ao criar contrato"); } finally { setBusy(false); }
  }
  return <div className="overlay" role="presentation" onMouseDown={onClose}><section className="panel" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}><header><div><p className="overline">IDENTIDADE ADMINISTRATIVA</p><h2>Novo contrato</h2></div><button type="button" onClick={onClose}>×</button></header><form onSubmit={submit}><div className="form-grid"><label>Unidade<select value={unit} onChange={(event) => setUnit(event.target.value)}>{reference.business_units.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Número interno<input name="number" required /></label></div><label>Cliente<select name="customer" required><option value="">Selecione</option>{reference.companies.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><div className="form-grid"><label>Assinatura<input name="signed_on" type="date" /></label><label>Início<input name="start_date" type="date" defaultValue={isoToday()} required /></label></div><label>Tipo<select name="type"><option value="recurring_service">Serviço recorrente</option><option value="project">Projeto</option><option value="retainer">Retainer</option><option value="other">Outro</option></select></label><label>Observação controlada<textarea name="notes" rows={3} /></label><p className="form-help">A criação não define valor nem emissor. Essas condições entram na primeira versão imutável.</p><div className="panel-actions"><button type="button" onClick={onClose}>Cancelar</button><button className="primary" disabled={busy} type="submit">{busy ? "Criando…" : "Criar contrato"}</button></div></form></section></div>;
}

function VersionModal({ reference, detail, apiUrl, token, onClose, onDone, onNotice }: { reference: ContractReference; detail: ContractDetail; apiUrl: string; token: string; onClose: () => void; onDone: (message: string) => Promise<void>; onNotice: Notice }) {
  const previous = detail.versions.at(-1);
  const initial = !previous;
  const products = reference.products_services.filter((item) => item.business_unit_id === detail.business_unit_id);
  const contacts = reference.contact_methods.filter((item) => item.company_id === detail.customer_company_id && item.kind === "email");
  const [services, setServices] = useState<string[]>(previous?.services.filter((item) => item.is_active && item.product_service_id).map((item) => item.product_service_id as string) ?? []);
  const [busy, setBusy] = useState(false);
  const minimumDate = initial ? detail.start_date : nextDay(previous.effective_from);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); const data = new FormData(event.currentTarget);
    try {
      const effective = String(data.get("effective_from"));
      const changeType = initial ? "initial" : String(data.get("change_type"));
      const amount = String(data.get("amount"));
      const body = {
        effective_from: effective,
        issuer_establishment_id: data.get("issuer"),
        currency: "BRL",
        billing_frequency: data.get("frequency"),
        pricing_model: data.get("pricing_model"),
        amount,
        billing_installments: data.get("pricing_model") === "annual" && data.get("frequency") === "monthly" ? 12 : null,
        billing_day: data.get("billing_day") ? Number(data.get("billing_day")) : null,
        payment_terms_days: data.get("terms") ? Number(data.get("terms")) : null,
        invoice_description: data.get("description") || null,
        adjustment_reference: data.get("adjustment") || null,
        adjustment_frequency: data.get("adjustment") ? "annual" : "none",
        adjustment_base_date: data.get("adjustment") ? effective : null,
        adjustment_applied_percentage: changeType === "adjustment" ? data.get("percentage") : null,
        adjustment_source: changeType === "adjustment" ? "manual" : "not_applied",
        change_type: changeType,
        change_reason: data.get("reason"),
        source: "ui",
        services: products.filter((item) => services.includes(item.id)).map((item) => ({ product_service_id: item.id, contractual_description: item.name, quantity: "1.000", unit_amount: amount, is_active: true })),
        financial_contacts: [{ contact_method_id: data.get("contact"), recipient_role: "primary", purpose: "billing", preferred_channel: "email" }]
      };
      const path = !initial && effective > isoToday() ? "schedule" : "versions";
      await request(apiUrl, token, `/api/v1/contracts/${detail.id}/${path}`, { method: "POST", body: JSON.stringify(body) }, true);
      await onDone(initial ? "Primeira versão publicada." : "Nova versão contratual publicada sem alterar o passado.");
    } catch (error) { onNotice("error", error instanceof Error ? error.message : "Falha ao publicar versão"); } finally { setBusy(false); }
  }
  return <div className="overlay" role="presentation" onMouseDown={onClose}><section className="panel version-panel" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}><header><div><p className="overline">{initial ? "PRIMEIRA CONFIGURAÇÃO" : "NOVA VERSÃO IMUTÁVEL"}</p><h2>{detail.internal_number}</h2></div><button type="button" onClick={onClose}>×</button></header><form onSubmit={submit}><div className="form-grid"><label>Início da vigência<input name="effective_from" type="date" min={minimumDate} defaultValue={minimumDate} required /></label><label>Motivo da alteração<select name="change_type" disabled={initial}><option value="initial">Configuração inicial</option><option value="value_change">Alteração de valor</option><option value="issuer_change">Alteração de emissor</option><option value="service_change">Inclusão/exclusão de serviço</option><option value="conditions_change">Alteração de condições</option><option value="adjustment">Reajuste aplicado</option><option value="renewal">Renovação</option></select></label></div><label>Estabelecimento fiscal emissor<select name="issuer" defaultValue={previous?.issuer_establishment_id ?? ""} required><option value="">Selecione</option>{reference.fiscal_establishments.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><div className="form-grid"><label>Modelo de valor<select name="pricing_model" defaultValue={previous?.pricing_model ?? "annual"}><option value="monthly">Mensal</option><option value="annual">Anual</option><option value="project">Projeto</option><option value="per_service">Por serviço</option><option value="other">Outro</option></select></label><label>Valor contratual<input name="amount" type="number" min="0" step=".01" defaultValue={previous?.amount ?? ""} required /></label></div><div className="form-grid"><label>Periodicidade de cobrança<select name="frequency" defaultValue={previous?.billing_frequency ?? "monthly"}><option value="monthly">Mensal</option><option value="annual">Anual</option><option value="one_time">Única</option><option value="other">Outra</option></select></label><label>Dia de referência<input name="billing_day" type="number" min="1" max="31" defaultValue={previous?.billing_day ?? 1} /></label></div><div className="form-grid"><label>Prazo de pagamento (dias)<input name="terms" type="number" min="0" defaultValue={previous?.payment_terms_days ?? 15} /></label><label>Referência de reajuste<input name="adjustment" defaultValue={previous?.adjustment_reference ?? ""} placeholder="IPCA, percentual fixo…" /></label></div><label>Percentual aplicado, se reajuste<input name="percentage" type="number" step=".000001" /></label><fieldset><legend>Serviços desta versão</legend><div className="check-list">{products.map((item) => <label key={item.id}><input type="checkbox" checked={services.includes(item.id)} onChange={() => setServices((current) => current.includes(item.id) ? current.filter((id) => id !== item.id) : [...current, item.id])} />{item.name}</label>)}</div></fieldset><label>Contato financeiro principal<select name="contact" required><option value="">Selecione</option>{contacts.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.value}</option>)}</select></label><label>Descrição futura de faturamento<textarea name="description" rows={2} defaultValue={previous?.invoice_description ?? ""} /></label><label>Justificativa auditável<textarea name="reason" rows={3} minLength={3} required /></label><div className="panel-actions"><button type="button" onClick={onClose}>Cancelar</button><button className="primary" disabled={busy || !services.length || !contacts.length} type="submit">{busy ? "Publicando…" : "Publicar versão"}</button></div></form></section></div>;
}

function ContractDrawer({ detail, apiUrl, token, onClose, onVersion, onOperation, onNotice }: { detail: ContractDetail; apiUrl: string; token: string; onClose: () => void; onVersion: () => void; onOperation: () => void; onNotice: Notice }) {
  const [lookupDate, setLookupDate] = useState(isoToday());
  const [lookup, setLookup] = useState<Version | null>(null);
  const ordered = useMemo(() => [...detail.versions].sort((a, b) => b.version_number - a.version_number), [detail.versions]);
  async function lookupConfiguration() {
    try {
      const result = await request<{ version: Version }>(apiUrl, token, `/api/v1/contracts/${detail.id}/configuration?date=${lookupDate}`);
      setLookup(result.version);
    } catch (error) { onNotice("error", error instanceof Error ? error.message : "Sem configuração nesta data"); }
  }
  return <div className="overlay drawer-overlay" role="presentation" onMouseDown={onClose}><section className="drawer contract-drawer" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}><header><div><p className="overline">CONTRATO · {operationalLabel(detail.current_operational_state).toUpperCase()}</p><h2>{detail.internal_number}</h2><p>{detail.customer_name} · {detail.business_unit_name}</p></div><button type="button" onClick={onClose}>×</button></header><div className="contract-drawer-actions"><button className="primary" type="button" onClick={onVersion}>+ Nova versão</button><button type="button" onClick={onOperation}>Suspender / retomar / encerrar</button></div><section className="contract-query"><h3>Configuração válida em uma data</h3><div><input type="date" value={lookupDate} onChange={(event) => setLookupDate(event.target.value)} /><button type="button" onClick={() => void lookupConfiguration()}>Consultar</button></div>{lookup && <p>v{lookup.version_number} · {lookup.issuer_name} · <strong>{brl(lookup.amount, lookup.currency)}</strong></p>}</section><section><h3>Versões contratuais</h3><div className="version-timeline">{ordered.map((item) => { const previous = detail.versions.find((candidate) => candidate.version_number === item.version_number - 1); return <article className={`version-card ${item.temporal_status}`} key={item.id}><header><span className={`version-badge ${item.temporal_status}`}>{item.temporal_status === "current" ? "ATUAL" : item.temporal_status === "scheduled" ? "FUTURA" : "HISTÓRICA"}</span><strong>Versão {item.version_number}</strong><small>{dateLabel(item.effective_from)} — {dateLabel(item.effective_until)}</small></header><div className="version-facts"><span><small>Emissor</small>{item.issuer_name}</span><span><small>Valor</small>{brl(item.amount, item.currency)}</span><span><small>Serviços ativos</small>{item.services.filter((service) => service.is_active).length}</span></div><ul>{versionDiff(item, previous).map((change) => <li key={change}>{change}</li>)}</ul><details><summary>Configuração completa e contatos</summary><p>{item.services.filter((service) => service.is_active).map((service) => service.contractual_description).join(" · ")}</p><p>{item.financial_contacts.map((contact) => `${contact.recipient_role}: ${contact.contact_value}`).join(" · ")}</p><code>sha256:{item.configuration_sha256.slice(0, 16)}…</code></details></article>; })}{!ordered.length && <p className="muted">Contrato em rascunho. Publique a primeira versão.</p>}</div></section><section><h3>Eventos operacionais</h3>{detail.operational_events.map((event) => <div className="timeline-item" key={event.id}><span>{dateLabel(event.effective_on)}</span><strong>{eventLabel(event.event_type)}</strong><small>{event.reason}</small></div>)}{!detail.operational_events.length && <p className="muted">Nenhuma suspensão, retomada, renovação ou encerramento.</p>}</section></section></div>;
}

function OperationModal({ detail, apiUrl, token, onClose, onDone, onNotice }: { detail: ContractDetail; apiUrl: string; token: string; onClose: () => void; onDone: (message: string) => Promise<void>; onNotice: Notice }) {
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); const data = new FormData(event.currentTarget); const operation = String(data.get("operation"));
    try {
      await request(apiUrl, token, `/api/v1/contracts/${detail.id}/${operation}`, { method: "POST", body: JSON.stringify({ effective_on: data.get("effective_on"), reason: data.get("reason"), source: "ui" }) }, true);
      await onDone(`Operação contratual ${operation} registrada com auditoria.`);
    } catch (error) { onNotice("error", error instanceof Error ? error.message : "Falha na operação"); } finally { setBusy(false); }
  }
  return <div className="overlay" role="presentation" onMouseDown={onClose}><section className="panel" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}><header><div><p className="overline">EVENTO OPERACIONAL</p><h2>{detail.internal_number}</h2></div><button type="button" onClick={onClose}>×</button></header><form onSubmit={submit}><label>Operação<select name="operation" defaultValue={detail.current_operational_state === "suspended" ? "resume" : "suspend"}><option value="suspend">Suspender</option><option value="resume">Retomar</option><option value="terminate">Encerrar</option></select></label><label>Vigência do evento<input name="effective_on" type="date" min={isoToday()} defaultValue={isoToday()} required /></label><label>Motivo auditável<textarea name="reason" rows={4} minLength={3} required /></label><p className="form-help">O evento não altera nem apaga versões contratuais. Operações retroativas exigirão um fluxo excepcional futuro.</p><div className="panel-actions"><button type="button" onClick={onClose}>Cancelar</button><button className="primary" disabled={busy || !detail.versions.length} type="submit">{busy ? "Registrando…" : "Registrar evento"}</button></div></form></section></div>;
}
