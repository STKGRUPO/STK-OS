"use client";

import { type DragEvent, type FormEvent, useCallback, useEffect, useRef, useState } from "react";

import ContractsWorkspace from "./contracts-workspace";
import BillingWorkspace from "./billing-workspace";
import ClientServicesPanel from "./client-services-panel";
import IdentityWorkspace from "./identity-workspace";
import OrganizationWorkspace from "./organization-workspace";
import TasksWorkspace from "./tasks-workspace";

const API_URL = process.env.NEXT_PUBLIC_STK_API_URL ?? "http://127.0.0.1:8000";

type Catalog = { id: string; code: string; name: string; business_unit_id?: string | null };
type Stage = { id: string; code: string; name: string; position: number; sla_days: number | null };
type Pipeline = { id: string; business_unit_id: string; code: string; name: string; stages: Stage[] };
type Reference = {
  business_units: Catalog[];
  lead_sources: Catalog[];
  products_services: Catalog[];
  loss_reasons: Catalog[];
  pipelines: Pipeline[];
};
type Task = { id: string; title: string; due_at: string; priority: string; status: string };
type Opportunity = {
  id: string;
  business_unit_id: string;
  pipeline_id: string;
  stage_id: string;
  company_id: string | null;
  title: string;
  status: string;
  value: string | null;
  currency: string;
  customer_name: string;
  person_ids: string[];
  product_names: string[];
  product_service_ids: string[];
  last_interaction_at: string | null;
  stage_entered_at: string;
  next_action: Task | null;
};
type Kanban = { pipeline: Pipeline; columns: { stage: Stage; opportunities: Opportunity[] }[] };
type Person = { id: string; full_name: string; business_unit_ids: string[] };
type Company = { id: string; legal_name: string; trade_name: string | null; business_unit_ids: string[] };
type SearchItem = {
  resource_type: "person" | "company" | "opportunity";
  id: string;
  title: string;
  subtitle: string | null;
};
type Detail = {
  id: string;
  resourceType: "person" | "company";
  title: string;
  subtitle: string;
  opportunities: Opportunity[];
  activities: { id: string; activity_type: string; summary: string; occurred_at: string }[];
  tasks: Task[];
};
type Profile = { actor_id: string; display_name: string; email: string; capabilities: string[]; business_unit_ids: string[] };
type Panel = "person" | "company" | "opportunity" | "import" | null;
type Notice = { kind: "success" | "error"; text: string } | null;

async function api<T>(path: string, token: string, init?: RequestInit, command = false): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
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

function money(value: string | null, currency = "BRL") {
  if (value === null) return "Valor a definir";
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency }).format(Number(value));
}

function shortDate(value: string) {
  return new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short" }).format(
    new Date(value)
  );
}

function daysSince(value: string, now: number) {
  return Math.max(0, Math.floor((now - new Date(value).getTime()) / 86_400_000));
}

export default function Home() {
  const [token, setToken] = useState("");
  const [email, setEmail] = useState("admin@stk-os.local");
  const [password, setPassword] = useState("");
  const [accessToken, setAccessToken] = useState("");
  const [firstAccess, setFirstAccess] = useState(false);
  const [recoveryOpen, setRecoveryOpen] = useState(false);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [reference, setReference] = useState<Reference | null>(null);
  const [pipelineId, setPipelineId] = useState("");
  const [kanban, setKanban] = useState<Kanban | null>(null);
  const [people, setPeople] = useState<Person[]>([]);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [panel, setPanel] = useState<Panel>(null);
  const [deal, setDeal] = useState<Opportunity | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [search, setSearch] = useState("");
  const [results, setResults] = useState<SearchItem[]>([]);
  const [notice, setNotice] = useState<Notice>(null);
  const [loading, setLoading] = useState(false);
  const [now] = useState(() => Date.now());
  const [workspace, setWorkspace] = useState<"crm" | "contracts" | "billing" | "tasks" | "users" | "group-companies">("crm");
  const searchRef = useRef<HTMLInputElement>(null);
  const showNotice = useCallback((kind: "success" | "error", text: string) => {
    setNotice({ kind, text });
  }, []);

  useEffect(() => {
    const queryToken = new URLSearchParams(window.location.search).get("access_token");
    if (queryToken) queueMicrotask(() => setAccessToken(queryToken));
    if (window.location.pathname === "/primeiro-acesso") {
      queueMicrotask(() => setFirstAccess(true));
    }
    const shortcut = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setWorkspace("crm");
        requestAnimationFrame(() => searchRef.current?.focus());
      }
    };
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  }, []);

  const pipeline = reference?.pipelines.find((item) => item.id === pipelineId) ?? null;
  const unit = reference?.business_units.find((item) => item.id === pipeline?.business_unit_id);
  const allDeals = kanban?.columns.flatMap((column) => column.opportunities) ?? [];
  const totalValue = allDeals.reduce((total, item) => total + Number(item.value ?? 0), 0);
  const overdue = allDeals.filter(
    (item) => item.next_action && new Date(item.next_action.due_at).getTime() < now
  ).length;

  async function loadBoard(activeToken: string, activePipeline: string) {
    setLoading(true);
    try {
      setKanban(await api<Kanban>(`/api/v1/crm/kanban/${activePipeline}`, activeToken));
    } catch (error) {
      setNotice({ kind: "error", text: error instanceof Error ? error.message : "Falha no Kanban" });
    } finally {
      setLoading(false);
    }
  }

  async function loadDirectory(activeToken: string) {
    const [personItems, companyItems] = await Promise.all([
      api<Person[]>("/api/v1/crm/people", activeToken),
      api<Company[]>("/api/v1/crm/companies", activeToken)
    ]);
    setPeople(personItems);
    setCompanies(companyItems);
  }

  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setNotice(null);
    try {
      const response = await fetch(`${API_URL}/api/v1/auth/token`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password })
      });
      if (!response.ok) throw new Error("E-mail ou senha inválidos");
      const session = (await response.json()) as { access_token: string };
      const [data, activeProfile] = await Promise.all([
        api<Reference>("/api/v1/crm/reference-data", session.access_token),
        api<Profile>("/api/v1/auth/me", session.access_token)
      ]);
      setToken(session.access_token);
      setProfile(activeProfile);
      setReference(data);
      setPipelineId(data.pipelines[0]?.id ?? "");
      await Promise.all([
        loadDirectory(session.access_token),
        data.pipelines[0]
          ? loadBoard(session.access_token, data.pipelines[0].id)
          : Promise.resolve()
      ]);
    } catch (error) {
      setNotice({ kind: "error", text: error instanceof Error ? error.message : "Falha no login" });
    } finally {
      setLoading(false);
    }
  }

  function chooseUnit(unitId: string) {
    const first = reference?.pipelines.find((item) => item.business_unit_id === unitId);
    if (first) {
      setPipelineId(first.id);
      void loadBoard(token, first.id);
    }
  }

  async function moveDeal(opportunityId: string, stageId: string) {
    if (!kanban || !token) return;
    const current = allDeals.find((item) => item.id === opportunityId);
    if (!current || current.stage_id === stageId) return;
    const previous = kanban;
    setKanban({
      ...kanban,
      columns: kanban.columns.map((column) => ({
        ...column,
        opportunities:
          column.stage.id === stageId
            ? [...column.opportunities, { ...current, stage_id: stageId }]
            : column.opportunities.filter((item) => item.id !== current.id)
      }))
    });
    try {
      await api(
        `/api/v1/crm/opportunities/${opportunityId}/stage`,
        token,
        { method: "PATCH", body: JSON.stringify({ stage_id: stageId, source: "ui" }) },
        true
      );
      setNotice({ kind: "success", text: "Etapa atualizada e registrada no histórico." });
    } catch (error) {
      setKanban(previous);
      setNotice({ kind: "error", text: error instanceof Error ? error.message : "Falha ao mover" });
    }
  }

  async function runSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || search.trim().length < 2) return;
    try {
      setResults(await api<SearchItem[]>(`/api/v1/crm/search?q=${encodeURIComponent(search)}`, token));
    } catch (error) {
      setNotice({ kind: "error", text: error instanceof Error ? error.message : "Falha na busca" });
    }
  }

  async function openResult(item: SearchItem) {
    if (item.resource_type === "opportunity") {
      const opportunity = allDeals.find((candidate) => candidate.id === item.id);
      if (opportunity) setDeal(opportunity);
      return;
    }
    try {
      const payload = await api<{
        person?: Person;
        company?: Company;
        opportunities: Opportunity[];
        activities: Detail["activities"];
        tasks: Task[];
      }>(
        `/api/v1/crm/${item.resource_type === "person" ? "people" : "companies"}/${item.id}/360`,
        token
      );
      const title = payload.person?.full_name ?? payload.company?.trade_name ?? payload.company?.legal_name ?? item.title;
      setDetail({
        id: item.id,
        resourceType: item.resource_type,
        title,
        subtitle: `${item.resource_type === "person" ? "Pessoa" : "Empresa"} · visão 360°`,
        opportunities: payload.opportunities,
        activities: payload.activities,
        tasks: payload.tasks
      });
      setResults([]);
    } catch (error) {
      setNotice({ kind: "error", text: error instanceof Error ? error.message : "Falha na visão 360°" });
    }
  }

  async function refreshed(message: string) {
    if (!token || !pipelineId) return;
    await Promise.all([loadBoard(token, pipelineId), loadDirectory(token)]);
    setPanel(null);
    setDeal(null);
    setNotice({ kind: "success", text: message });
  }

  if (!token) {
    if (accessToken || firstAccess) return <PasswordDefinition token={accessToken} onDone={() => { setAccessToken(""); setFirstAccess(false); window.history.replaceState({}, "", "/"); setNotice({ kind: "success", text: accessToken ? "Senha definida. Entre com suas credenciais." : "Acesso criado. Entre com suas credenciais." }); }} />;
    return (
      <main className="login-shell">
        <section className="login-story">
          <div className="brand-mark">STK</div>
          <p className="overline">GRUPO STK · CRM VERTICAL</p>
          <h1>Relacionamentos claros. Próximas ações visíveis.</h1>
          <p>Um cadastro canônico para MR, STK Lab e Stelli, com histórico auditável.</p>
          <div className="login-proof"><span>03 unidades</span><span>01 cliente</span><span>360° de contexto</span></div>
        </section>
        <section className="login-card">
          <p className="overline">ACESSO ADMINISTRATIVO</p>
          <h2>Entrar no STK OS</h2>
          <p className="muted">Use somente a identidade local deste ambiente.</p>
          <form onSubmit={login}>
            <label>E-mail<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} /></label>
            <label>Senha<input type="password" minLength={12} required value={password} onChange={(event) => setPassword(event.target.value)} /></label>
            <button className="primary" disabled={loading} type="submit">{loading ? "Validando…" : "Entrar no CRM"}</button>
          </form>
          <button className="login-link" type="button" onClick={() => setRecoveryOpen((value) => !value)}>Esqueci minha senha</button>
          {recoveryOpen && <RecoveryRequest email={email} onEmail={setEmail} onNotice={setNotice} />}
          {notice && <p className={`notice ${notice.kind}`}>{notice.text}</p>}
          <div className="api-address">API local · {API_URL}</div>
        </section>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="lovable-brand"><span>STK</span><div><strong>STK OS</strong><small>Ambiente operacional</small></div></div>
        <nav aria-label="Navegação principal">
          <button className={`nav-item ${workspace === "crm" ? "active" : ""}`} type="button" onClick={() => setWorkspace("crm")}><span>◫</span>CRM</button>
          <button className={`nav-item ${workspace === "contracts" ? "active" : ""}`} type="button" onClick={() => setWorkspace("contracts")}><span>▤</span>Contratos</button>
          <button className={`nav-item ${workspace === "billing" ? "active" : ""}`} type="button" onClick={() => setWorkspace("billing")}><span>▦</span>Faturar</button>
          <button className={`nav-item ${workspace === "tasks" ? "active" : ""}`} type="button" onClick={() => setWorkspace("tasks")}><span>✓</span>Tarefas</button>
          {(profile?.capabilities.includes("identity:manage") || profile?.capabilities.includes("organization:read")) && <span className="nav-section-label">Administração</span>}
          {profile?.capabilities.includes("identity:manage") && <button className={`nav-item ${workspace === "users" ? "active" : ""}`} type="button" onClick={() => setWorkspace("users")}><span>○</span>Usuários</button>}
          {profile?.capabilities.includes("organization:read") && <button className={`nav-item ${workspace === "group-companies" ? "active" : ""}`} type="button" onClick={() => setWorkspace("group-companies")}><span>◇</span>Empresas do Grupo</button>}
        </nav>
        <div className="sidebar-principle"><span>PRINCÍPIO</span><p>O sistema sabe tudo.<br />A tela mostra só o que importa agora.</p></div>
        <div className="sidebar-footer"><strong>{profile?.display_name}</strong><span>{profile?.email}</span><button type="button" onClick={() => { setToken(""); setProfile(null); }}>Sair</button></div>
      </aside>
      {workspace === "contracts" ? <ContractsWorkspace apiUrl={API_URL} token={token} onNotice={showNotice} /> : workspace === "billing" ? <BillingWorkspace apiUrl={API_URL} token={token} onNotice={showNotice} /> : workspace === "tasks" ? <TasksWorkspace apiUrl={API_URL} token={token} units={reference?.business_units ?? []} activeUnitId={pipeline?.business_unit_id ?? ""} onNotice={showNotice} /> : workspace === "users" ? <IdentityWorkspace apiUrl={API_URL} token={token} units={reference?.business_units ?? []} onNotice={showNotice} /> : workspace === "group-companies" ? <OrganizationWorkspace apiUrl={API_URL} token={token} units={reference?.business_units ?? []} canWrite={profile?.capabilities.includes("organization:write") ?? false} onNotice={showNotice} /> : <section className="workspace">
        <header className="topbar">
          <div><p className="overline">CRM · GRUPO STK</p><h1>{unit?.name ?? "Pipeline comercial"}</h1></div>
          <form className="search" onSubmit={runSearch}><span>⌕</span><input ref={searchRef} aria-label="Busca global" placeholder="Buscar pessoa, empresa, contato ou negócio" value={search} onChange={(event) => setSearch(event.target.value)} /><kbd>Ctrl K</kbd><button type="submit">Buscar</button></form>
          <button className="primary new-button" type="button" onClick={() => setPanel("opportunity")}>+ Novo negócio</button>
        </header>
        {results.length > 0 && <div className="search-results">{results.map((item) => <button key={`${item.resource_type}-${item.id}`} type="button" onClick={() => void openResult(item)}><span className="result-icon">{item.resource_type === "person" ? "P" : item.resource_type === "company" ? "E" : "N"}</span><span><strong>{item.title}</strong><small>{item.subtitle}</small></span></button>)}</div>}
        <div className="unit-tabs">
          {reference?.business_units.map((item) => <button className={item.id === pipeline?.business_unit_id ? "active" : ""} key={item.id} type="button" onClick={() => chooseUnit(item.id)}>{item.name}</button>)}
          {(reference?.pipelines.filter((item) => item.business_unit_id === pipeline?.business_unit_id).length ?? 0) > 1 && <select aria-label="Pipeline" value={pipelineId} onChange={(event) => { setPipelineId(event.target.value); void loadBoard(token, event.target.value); }}>{reference?.pipelines.filter((item) => item.business_unit_id === pipeline?.business_unit_id).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>}
        </div>
        <section className="metrics"><article><span>NEGÓCIOS ABERTOS</span><strong>{allDeals.length}</strong><small>neste pipeline</small></article><article><span>VALOR EM PIPELINE</span><strong>{money(String(totalValue))}</strong><small>estimativa aberta</small></article><article className={overdue ? "attention" : ""}><span>AÇÕES VENCIDAS</span><strong>{overdue}</strong><small>{overdue ? "pedem atenção" : "tudo em dia"}</small></article></section>
        <section className={`kanban ${loading ? "loading" : ""}`}>
          {kanban?.columns.map((column) => <article className="kanban-column" key={column.stage.id} onDragOver={(event) => event.preventDefault()} onDrop={(event: DragEvent<HTMLElement>) => { event.preventDefault(); void moveDeal(event.dataTransfer.getData("text/opportunity"), column.stage.id); }}>
            <header><span className="stage-index">{String(column.stage.position).padStart(2, "0")}</span><h2>{column.stage.name}</h2><span className="count">{column.opportunities.length}</span></header>
            <div className="card-list">{column.opportunities.map((item) => { const isOverdue = Boolean(item.next_action && new Date(item.next_action.due_at).getTime() < now); return <button className="deal-card" draggable key={item.id} type="button" onClick={() => setDeal(item)} onDragStart={(event) => event.dataTransfer.setData("text/opportunity", item.id)}><span className="deal-unit">{item.product_names.join(" · ") || "Serviço a definir"}</span><strong>{item.title}</strong><span className="customer">{item.customer_name}</span><span className="deal-value">{money(item.value, item.currency)}</span><span className="deal-meta"><span>{daysSince(item.stage_entered_at, now)}d na etapa</span><span>{item.last_interaction_at ? `Interação ${shortDate(item.last_interaction_at)}` : "Sem interação"}</span></span><span className={`next-action ${isOverdue ? "overdue" : ""}`}><span>{isOverdue ? "!" : "→"}</span>{item.next_action ? `${shortDate(item.next_action.due_at)} · ${item.next_action.title}` : "Sem próxima ação"}</span></button>; })}{column.opportunities.length === 0 && <div className="empty-column">Arraste um negócio para esta etapa</div>}</div>
          </article>)}
        </section>
      </section>}
      {notice && <button className={`toast ${notice.kind}`} type="button" onClick={() => setNotice(null)}>{notice.text}<span>×</span></button>}
      {panel && reference && <CreatePanel panel={panel} token={token} reference={reference} people={people} companies={companies} currentPipeline={pipeline} onClose={() => setPanel(null)} onDone={refreshed} onError={(text) => setNotice({ kind: "error", text })} />}
      {deal && reference && <DealDrawer opportunity={deal} reference={reference} token={token} onClose={() => setDeal(null)} onDone={refreshed} onError={(text) => setNotice({ kind: "error", text })} />}
      {detail && reference && profile && <DetailDrawer detail={detail} token={token} reference={reference} profile={profile} onNotice={showNotice} onClose={() => setDetail(null)} />}
    </main>
  );
}

function PasswordDefinition({ token, onDone }: { token: string; onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(""); const values = new FormData(event.currentTarget);
    const email = String(values.get("email"));
    const password = String(values.get("password"));
    if (password !== String(values.get("confirmation"))) { setError("As senhas não coincidem."); setBusy(false); return; }
    const response = await fetch(`${API_URL}/api/v1/auth/password/define`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password, ...(token ? { token } : {}) }) });
    if (!response.ok) { const payload = await response.json().catch(() => null) as { detail?: string } | null; setError(payload?.detail ?? "Link inválido ou expirado"); setBusy(false); return; }
    onDone();
  }
  return <main className="login-shell"><section className="login-story"><div className="brand-mark">STK</div><p className="overline">PRIMEIRO ACESSO · RECUPERAÇÃO</p><h1>Sua senha pertence somente a você.</h1><p>{token ? "O link é temporário, de uso único e não contém uma senha criada pelo administrador." : "Crie seu acesso com seu e-mail e uma senha segura."}</p></section><section className="login-card"><p className="overline">DEFINIÇÃO SEGURA</p><h2>{token ? "Definir minha senha" : "Criar meu acesso"}</h2><form onSubmit={submit}><label>E-mail<input name="email" type="email" required /></label><label>Nova senha<input name="password" type="password" minLength={12} required /></label><label>Confirmar senha<input name="confirmation" type="password" minLength={12} required /></label><button className="primary" disabled={busy} type="submit">{busy ? "Salvando…" : token ? "Definir senha" : "Criar acesso"}</button></form>{error && <p className="notice error">{error}</p>}</section></main>;
}

function RecoveryRequest({ email, onEmail, onNotice }: { email: string; onEmail: (value: string) => void; onNotice: (notice: Notice) => void }) {
  async function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const response = await fetch(`${API_URL}/api/v1/auth/password-reset/request`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email }) }); onNotice({ kind: response.ok ? "success" : "error", text: response.ok ? "Se a conta estiver ativa, a recuperação será disponibilizada pelo canal seguro." : "Não foi possível solicitar a recuperação." }); }
  return <form className="recovery-form" onSubmit={submit}><label>E-mail da conta<input type="email" value={email} onChange={(event) => onEmail(event.target.value)} required /></label><button type="submit">Solicitar recuperação</button></form>;
}

function CreatePanel({ panel, token, reference, people, companies, currentPipeline, onClose, onDone, onError }: { panel: Exclude<Panel, null>; token: string; reference: Reference; people: Person[]; companies: Company[]; currentPipeline: Pipeline | null; onClose: () => void; onDone: (message: string) => Promise<void>; onError: (message: string) => void }) {
  const [busy, setBusy] = useState(false);
  const [unitIds, setUnitIds] = useState<string[]>([currentPipeline?.business_unit_id ?? reference.business_units[0]?.id ?? ""]);
  const [opportunityUnit, setOpportunityUnit] = useState(currentPipeline?.business_unit_id ?? reference.business_units[0]?.id ?? "");
  const [formPipeline, setFormPipeline] = useState(currentPipeline?.id ?? "");
  const pipelines = reference.pipelines.filter((item) => item.business_unit_id === opportunityUnit);
  const selectedPipeline = reference.pipelines.find((item) => item.id === formPipeline) ?? pipelines[0];
  const toggleUnit = (id: string) => setUnitIds((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); const values = new FormData(event.currentTarget);
    try {
      if (panel === "person" || panel === "company") {
        const contact = String(values.get("contact") ?? "");
        const body = panel === "person" ? { full_name: values.get("name"), city: values.get("city") || null, state_code: values.get("state") || null, business_unit_ids: unitIds, lead_source_id: reference.lead_sources[0]?.id, contacts: contact ? [{ kind: contact.includes("@") ? "email" : "phone", value: contact, is_primary: true }] : [] } : { legal_name: values.get("legal_name"), trade_name: values.get("trade_name") || null, city: values.get("city") || null, state_code: values.get("state") || null, business_unit_ids: unitIds, lead_source_id: reference.lead_sources[0]?.id, contacts: contact ? [{ kind: contact.includes("@") ? "email" : "phone", value: contact, is_primary: true }] : [] };
        await api(`/api/v1/crm/${panel === "person" ? "people" : "companies"}`, token, { method: "POST", body: JSON.stringify(body) }, true);
        await onDone(panel === "person" ? "Pessoa criada como cadastro canônico." : "Empresa criada e vinculada às unidades.");
      } else if (panel === "opportunity" && selectedPipeline) {
        const personId = String(values.get("person_id") ?? ""); const companyId = String(values.get("company_id") ?? "");
        await api("/api/v1/crm/opportunities", token, { method: "POST", body: JSON.stringify({ business_unit_id: opportunityUnit, pipeline_id: selectedPipeline.id, stage_id: selectedPipeline.stages[0]?.id, person_ids: personId ? [personId] : [], company_id: companyId || null, title: values.get("title"), value: values.get("value") || null, lead_source_id: values.get("source_id"), product_service_ids: values.get("product_id") ? [values.get("product_id")] : [], next_action_title: values.get("next_action"), next_action_due_at: new Date(String(values.get("due_at"))).toISOString() }) }, true);
        await onDone("Negócio criado com próxima ação e histórico inicial.");
      } else if (panel === "import") {
        const rows = JSON.parse(String(values.get("rows"))) as unknown; if (!Array.isArray(rows)) throw new Error("O conteúdo deve ser uma lista JSON.");
        const result = await api<{ created_rows: number; matched_rows: number; failed_rows: number }>("/api/v1/crm/imports", token, { method: "POST", body: JSON.stringify({ source_label: values.get("source_label"), rows }) }, true);
        await onDone(`Importação: ${result.created_rows} criados, ${result.matched_rows} vinculados, ${result.failed_rows} para revisão.`);
      }
    } catch (error) { onError(error instanceof Error ? error.message : "Não foi possível salvar"); } finally { setBusy(false); }
  }

  const products = reference.products_services.filter((item) => item.business_unit_id === opportunityUnit);
  const availablePeople = people.filter((item) => item.business_unit_ids.includes(opportunityUnit));
  const availableCompanies = companies.filter((item) => item.business_unit_ids.includes(opportunityUnit));
  const title = panel === "person" ? "Pessoa" : panel === "company" ? "Empresa" : panel === "opportunity" ? "Negócio" : "Importação pequena";

  return <div className="overlay" role="presentation" onMouseDown={onClose}><section className="panel" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}><header><div><p className="overline">NOVO REGISTRO</p><h2>{title}</h2></div><button type="button" onClick={onClose}>×</button></header><form onSubmit={submit}>
    {panel === "person" && <><label>Nome completo<input name="name" required minLength={2} /></label><label>Telefone ou e-mail<input name="contact" /></label><div className="form-grid"><label>Cidade<input name="city" /></label><label>UF<input name="state" maxLength={2} /></label></div></>}
    {panel === "company" && <><label>Razão social<input name="legal_name" required minLength={2} /></label><label>Nome fantasia<input name="trade_name" /></label><label>Telefone ou e-mail<input name="contact" /></label><div className="form-grid"><label>Cidade<input name="city" /></label><label>UF<input name="state" maxLength={2} /></label></div></>}
    {(panel === "person" || panel === "company") && <fieldset><legend>Relacionar com unidades</legend><div className="check-list">{reference.business_units.map((item) => <label key={item.id}><input type="checkbox" checked={unitIds.includes(item.id)} onChange={() => toggleUnit(item.id)} />{item.name}</label>)}</div></fieldset>}
    {panel === "opportunity" && <><label>Unidade<select value={opportunityUnit} onChange={(event) => { const value = event.target.value; setOpportunityUnit(value); setFormPipeline(reference.pipelines.find((item) => item.business_unit_id === value)?.id ?? ""); }}>{reference.business_units.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Pipeline<select value={selectedPipeline?.id ?? ""} onChange={(event) => setFormPipeline(event.target.value)}>{pipelines.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Título<input name="title" required /></label><div className="form-grid"><label>Pessoa<select name="person_id"><option value="">Não informada</option>{availablePeople.map((item) => <option key={item.id} value={item.id}>{item.full_name}</option>)}</select></label><label>Empresa<select name="company_id"><option value="">Não informada</option>{availableCompanies.map((item) => <option key={item.id} value={item.id}>{item.trade_name || item.legal_name}</option>)}</select></label></div><div className="form-grid"><label>Produto / serviço<select name="product_id"><option value="">A definir</option>{products.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Valor<input name="value" type="number" min="0" step=".01" /></label></div><label>Origem<select name="source_id">{reference.lead_sources.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Próxima ação<input name="next_action" required /></label><label>Prazo<input name="due_at" type="datetime-local" required /></label></>}
    {panel === "import" && <><p className="form-help">Até 100 linhas. A evidência guarda hash e resultado, não o payload.</p><label>Identificação da fonte<input name="source_label" defaultValue="Importação controlada" required /></label><label>Linhas JSON<textarea name="rows" rows={12} required placeholder='[{"entity_type":"person","person":{"full_name":"Pessoa sintética","business_unit_ids":["..."]}}]' /></label></>}
    <div className="panel-actions"><button type="button" onClick={onClose}>Cancelar</button><button className="primary" disabled={busy || ((panel === "person" || panel === "company") && !unitIds.length)} type="submit">{busy ? "Salvando…" : "Salvar"}</button></div>
  </form></section></div>;
}

function DealDrawer({ opportunity, reference, token, onClose, onDone, onError }: { opportunity: Opportunity; reference: Reference; token: string; onClose: () => void; onDone: (message: string) => Promise<void>; onError: (message: string) => void }) {
  const [busy, setBusy] = useState(false);
  const reasons = reference.loss_reasons.filter((item) => item.business_unit_id === opportunity.business_unit_id);
  async function add(path: "tasks" | "activities", event: FormEvent<HTMLFormElement>) { event.preventDefault(); setBusy(true); const values = new FormData(event.currentTarget); try { const body = path === "tasks" ? { business_unit_id: opportunity.business_unit_id, opportunity_id: opportunity.id, title: values.get("title"), due_at: new Date(String(values.get("due_at"))).toISOString() } : { business_unit_id: opportunity.business_unit_id, opportunity_id: opportunity.id, company_id: opportunity.company_id, person_id: opportunity.person_ids[0] ?? null, activity_type: values.get("type"), occurred_at: new Date().toISOString(), summary: values.get("summary"), origin: "ui", performed_by: "human" }; await api(`/api/v1/crm/${path}`, token, { method: "POST", body: JSON.stringify(body) }, true); await onDone(path === "tasks" ? "Nova próxima ação registrada." : "Interação adicionada à linha do tempo."); } catch (error) { onError(error instanceof Error ? error.message : "Falha ao registrar"); } finally { setBusy(false); } }
  async function close(status: "won" | "lost", reason?: string) { setBusy(true); try { await api(`/api/v1/crm/opportunities/${opportunity.id}/status`, token, { method: "PATCH", body: JSON.stringify({ status, loss_reason_id: reason ?? null }) }, true); await onDone(status === "won" ? "Negócio marcado como ganho." : "Perda registrada com motivo."); } catch (error) { onError(error instanceof Error ? error.message : "Falha ao fechar negócio"); } finally { setBusy(false); } }
  return <div className="overlay drawer-overlay" role="presentation" onMouseDown={onClose}><section className="drawer" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}><header><div><p className="overline">NEGÓCIO · {opportunity.status.toUpperCase()}</p><h2>{opportunity.title}</h2><p>{opportunity.customer_name}</p></div><button type="button" onClick={onClose}>×</button></header><div className="deal-summary"><div><span>Valor</span><strong>{money(opportunity.value)}</strong></div><div><span>Produtos</span><strong>{opportunity.product_names.join(", ") || "A definir"}</strong></div><div><span>Próxima ação</span><strong>{opportunity.next_action?.title ?? "Sem ação"}</strong></div></div><form className="mini-form" onSubmit={(event) => void add("activities", event)}><h3>Registrar interação</h3><div className="form-grid"><select name="type"><option value="call">Ligação</option><option value="email">E-mail</option><option value="meeting">Reunião</option><option value="follow_up">Follow-up</option><option value="note">Observação</option></select><input name="summary" placeholder="Resumo objetivo" required /></div><button disabled={busy} type="submit">Adicionar à linha do tempo</button></form><form className="mini-form" onSubmit={(event) => void add("tasks", event)}><h3>Agendar próxima ação</h3><input name="title" placeholder="O que precisa ser feito?" required /><input name="due_at" type="datetime-local" required /><button disabled={busy} type="submit">Criar tarefa</button></form><div className="close-actions"><button className="won" disabled={busy} type="button" onClick={() => void close("won")}>Marcar como ganho</button><select aria-label="Registrar perda" defaultValue="" disabled={busy} onChange={(event) => { if (event.target.value) void close("lost", event.target.value); }}><option value="" disabled>Registrar perda…</option>{reasons.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></div></section></div>;
}

function DetailDrawer({ detail, token, reference, profile, onNotice, onClose }: { detail: Detail; token: string; reference: Reference; profile: Profile; onNotice: (kind: "success" | "error", text: string) => void; onClose: () => void }) {
  return <div className="overlay drawer-overlay" role="presentation" onMouseDown={onClose}><section className="drawer detail-drawer client-360-drawer" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}><header><div><p className="overline">{detail.subtitle}</p><h2>{detail.title}</h2></div><button type="button" onClick={onClose}>×</button></header>{detail.resourceType === "company" && <ClientServicesPanel apiUrl={API_URL} token={token} companyId={detail.id} actorId={profile.actor_id} units={reference.business_units} products={reference.products_services} onNotice={onNotice} />}<section><h3>Negócios</h3>{detail.opportunities.length ? detail.opportunities.map((item) => <div className="timeline-item" key={item.id}><span>{item.status}</span><strong>{item.title}</strong><small>{money(item.value)}</small></div>) : <p className="muted">Nenhum negócio relacionado.</p>}</section><section><h3>Linha do tempo</h3>{detail.activities.length ? detail.activities.map((item) => <div className="timeline-item" key={item.id}><span>{shortDate(item.occurred_at)}</span><strong>{item.summary}</strong><small>{item.activity_type}</small></div>) : <p className="muted">Nenhuma interação.</p>}</section><section><h3>Tarefas</h3>{detail.tasks.length ? detail.tasks.map((item) => <div className="timeline-item" key={item.id}><span>{shortDate(item.due_at)}</span><strong>{item.title}</strong><small>{item.status}</small></div>) : <p className="muted">Nenhuma tarefa.</p>}</section></section></div>;
}
