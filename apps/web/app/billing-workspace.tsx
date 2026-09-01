"use client";

import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";

type Notice = (kind: "success" | "error", text: string) => void;
type RefItem = { id: string; name: string; business_unit_id?: string | null; primary_establishment_id?: string | null };
type References = { business_units: RefItem[]; companies: RefItem[]; fiscal_establishments: RefItem[]; products_services: RefItem[] };
type RunContract = {
  contract_id: string;
  contract_number: string;
  customer_name: string;
  billing_item_id: string | null;
  outcome: string;
  reason_code: string | null;
  reason_detail: string | null;
};
type Run = {
  id: string;
  business_unit_id: string;
  business_unit_name: string;
  competence_month: string;
  run_type: string;
  status: string;
  operational_timezone: string;
  rule_version: string;
  metrics: Record<string, number>;
  started_at: string;
  completed_at: string | null;
  contracts: RunContract[];
};
type Item = {
  id: string;
  source_type: string;
  contract_id: string | null;
  contract_number: string;
  contract_version_id: string | null;
  contract_version_number: number | null;
  competence_month: string;
  business_unit_id: string;
  business_unit_name: string;
  customer_company_id: string;
  customer_name: string;
  issuer_name: string | null;
  currency: string | null;
  gross_amount: string | null;
  status: string;
  blocking_code: string | null;
  blocking_reason: string | null;
  snapshot_sha256: string;
};
type Detail = Item & {
  snapshot: Record<string, unknown>;
  history: { kind: string; name: string; occurred_at: string; status: string | null }[];
};
type Summary = {
  competence_month: string;
  predicted_gross_amount: string;
  eligible_contracts: number;
  blocked_contracts: number;
  blocked_gross_amount: string;
  ready_contracts: number;
};
type FiscalDocument = { id: string; document_type: string; content_type: string; status: string; download_path: string | null; filename: string | null };
type Issuance = {
  id: string;
  billing_item_id: string;
  status: string;
  issuer_name: string;
  dps_number: number;
  dps_id: string;
  nfse_number: string | null;
  access_key: string | null;
  error_code: string | null;
  error_message: string | null;
  documents: FiscalDocument[];
  attempts: { attempt_number: number; operation: string; outcome: string; error_code: string | null; started_at: string }[];
};

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

function saoPauloCompetence() {
  const parts = new Intl.DateTimeFormat("en", {
    timeZone: "America/Sao_Paulo",
    year: "numeric",
    month: "2-digit"
  }).formatToParts(new Date());
  const year = parts.find((part) => part.type === "year")?.value ?? "2026";
  const month = parts.find((part) => part.type === "month")?.value ?? "01";
  return `${year}-${month}`;
}

function money(value: string | null, currency = "BRL") {
  if (value === null) return "indisponível";
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency }).format(Number(value));
}

function statusLabel(value: string) {
  return ({
    ready: "Pronto",
    blocked: "Bloqueado",
    requested: "Solicitado",
    completed: "Concluído",
    cancelled: "Cancelado",
    completed_with_exceptions: "Concluído com exceções"
    ,uncertain: "Resultado incerto"
    ,rejected: "Rejeitada"
    ,external_unavailable: "Provedor indisponível"
    ,configuration_error: "Configuração inválida"
    ,document_error: "Emitida · documento pendente"
  } as Record<string, string>)[value] ?? value;
}

function issuanceStatusLabel(value: string) {
  return value === "completed" ? "Autorizada" : value === "document_error" ? "Autorizada · documento pendente" : statusLabel(value);
}

export default function BillingWorkspace({
  apiUrl,
  token,
  onNotice
}: {
  apiUrl: string;
  token: string;
  onNotice: Notice;
}) {
  const [references, setReferences] = useState<References | null>(null);
  const [competence, setCompetence] = useState(saoPauloCompetence);
  const [unit, setUnit] = useState("");
  const [customer, setCustomer] = useState("");
  const [status, setStatus] = useState("");
  const [runs, setRuns] = useState<Run[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [selectedRun, setSelectedRun] = useState<Run | null>(null);
  const [selectedItem, setSelectedItem] = useState<Detail | null>(null);
  const [issuance, setIssuance] = useState<Issuance | null>(null);
  const [issuing, setIssuing] = useState("");
  const [oneTimeOpen, setOneTimeOpen] = useState(false);
  const [oneTimeUnit, setOneTimeUnit] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    const itemParams = new URLSearchParams({ competence_month: competence });
    const runParams = new URLSearchParams({ competence_month: competence });
    const summaryParams = new URLSearchParams({ competence_month: competence });
    if (unit) {
      itemParams.set("business_unit_id", unit);
      runParams.set("business_unit_id", unit);
      summaryParams.set("business_unit_id", unit);
    }
    if (customer) itemParams.set("customer_company_id", customer);
    if (status) itemParams.set("status", status);
    try {
      const [runData, itemData, summaryData] = await Promise.all([
        request<Run[]>(apiUrl, token, `/api/v1/billing/runs?${runParams}`),
        request<Item[]>(apiUrl, token, `/api/v1/billing/items?${itemParams}`),
        request<Summary>(apiUrl, token, `/api/v1/billing/summary?${summaryParams}`)
      ]);
      setRuns(runData);
      setItems(itemData);
      setSummary(summaryData);
    } catch (error) {
      onNotice("error", error instanceof Error ? error.message : "Falha ao consultar faturamento");
    } finally {
      setLoading(false);
    }
  }, [apiUrl, token, competence, unit, customer, status, onNotice]);

  useEffect(() => {
    let active = true;
    async function initialLoad() {
      try {
        const activeCompetence = saoPauloCompetence();
        const [data, runData, itemData, summaryData] = await Promise.all([
          request<References>(apiUrl, token, "/api/v1/contracts/reference-data"),
          request<Run[]>(apiUrl, token, `/api/v1/billing/runs?competence_month=${activeCompetence}`),
          request<Item[]>(apiUrl, token, `/api/v1/billing/items?competence_month=${activeCompetence}`),
          request<Summary>(apiUrl, token, `/api/v1/billing/summary?competence_month=${activeCompetence}`)
        ]);
        if (active) {
          setReferences(data);
          setRuns(runData);
          setItems(itemData);
          setSummary(summaryData);
        }
      } catch (error) {
        if (active) {
          onNotice("error", error instanceof Error ? error.message : "Falha nas referências");
        }
      } finally {
        if (active) setLoading(false);
      }
    }
    void initialLoad();
    return () => { active = false; };
  }, [apiUrl, token, onNotice]);

  const grossTotal = useMemo(
    () => items.reduce((total, item) => total + Number(item.gross_amount ?? 0), 0),
    [items]
  );

  async function generate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!unit) {
      onNotice("error", "Selecione uma unidade para gerar a competência.");
      return;
    }
    setLoading(true);
    try {
      const run = await request<Run>(apiUrl, token, "/api/v1/billing/runs", {
        method: "POST",
        body: JSON.stringify({
          business_unit_id: unit,
          competence_month: competence,
          run_type: "manual"
        })
      }, true);
      onNotice("success", `Competência ${run.competence_month} processada sem duplicar obrigações.`);
      await load();
      setSelectedRun(await request<Run>(apiUrl, token, `/api/v1/billing/runs/${run.id}`));
    } catch (error) {
      onNotice("error", error instanceof Error ? error.message : "Falha ao gerar competência");
      setLoading(false);
    }
  }

  async function openRun(id: string) {
    try {
      setSelectedRun(await request<Run>(apiUrl, token, `/api/v1/billing/runs/${id}`));
    } catch (error) {
      onNotice("error", error instanceof Error ? error.message : "Falha ao abrir execução");
    }
  }

  async function openItem(id: string) {
    try {
      setSelectedItem(await request<Detail>(apiUrl, token, `/api/v1/billing/items/${id}`));
      try {
        setIssuance(await request<Issuance>(apiUrl, token, `/api/v1/billing/items/${id}/issuance`));
      } catch {
        setIssuance(null);
      }
    } catch (error) {
      onNotice("error", error instanceof Error ? error.message : "Falha ao abrir obrigação");
    }
  }

  async function emitItem(item: Item | Detail) {
    if (item.status !== "ready") return;
    const confirmed = window.confirm([
      "Confirmar emissão de NFS-e?",
      `Cliente: ${item.customer_name}`,
      `Serviço: ${item.contract_number}`,
      `Valor: ${money(item.gross_amount, item.currency ?? "BRL")}`,
      `Competência/referência: ${item.competence_month}`,
      `Emissor: ${item.issuer_name ?? "Indisponível"}`
    ].join("\n"));
    if (!confirmed) return;
    setIssuing(item.id);
    try {
      const result = await request<Issuance>(apiUrl, token, `/api/v1/billing/items/${item.id}/issue`, { method: "POST", body: "{}" }, true);
      setIssuance(result);
      onNotice(result.status === "completed" ? "success" : "error", result.status === "completed" ? `NFS-e ${result.nfse_number} emitida.` : result.error_message ?? statusLabel(result.status));
      await load();
      setSelectedItem(await request<Detail>(apiUrl, token, `/api/v1/billing/items/${item.id}`));
    } catch (error) {
      onNotice("error", error instanceof Error ? error.message : "Não foi possível emitir a NFS-e");
    } finally {
      setIssuing("");
    }
  }

  async function reconcile() {
    if (!issuance) return;
    setIssuing(issuance.billing_item_id);
    try {
      const result = await request<Issuance>(apiUrl, token, `/api/v1/fiscal/issuances/${issuance.id}/reconcile`, { method: "POST", body: JSON.stringify({ resend_if_confirmed_not_found: false }) }, true);
      setIssuance(result);
      onNotice(result.status === "completed" ? "success" : "error", result.status === "completed" ? "Emissão reconciliada com sucesso." : statusLabel(result.status));
      await load();
    } catch (error) {
      onNotice("error", error instanceof Error ? error.message : "Falha na reconciliação");
    } finally { setIssuing(""); }
  }

  async function downloadDocument(document: FiscalDocument) {
    if (!document.download_path) return;
    try {
      const response = await fetch(`${apiUrl}${document.download_path}`, { headers: { Authorization: `Bearer ${token}` } });
      if (!response.ok) throw new Error("Documento fiscal indisponível");
      const url = URL.createObjectURL(await response.blob());
      const anchor = window.document.createElement("a");
      anchor.href = url; anchor.download = document.filename ?? `NFSE.${document.content_type.includes("xml") ? "xml" : "pdf"}`; anchor.click();
      URL.revokeObjectURL(url);
    } catch (error) { onNotice("error", error instanceof Error ? error.message : "Falha no documento"); }
  }

  async function createOneTime(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    setLoading(true);
    try {
      const result = await request<{ billing_item_id: string; billing_status: string }>(apiUrl, token, "/api/v1/billing/one-time", { method: "POST", body: JSON.stringify({
        business_unit_id: values.get("business_unit_id"), customer_company_id: values.get("customer_company_id"),
        product_service_id: values.get("product_service_id") || null, service_name: values.get("service_name"),
        description: values.get("description"), reference: values.get("reference"), service_date: values.get("service_date"),
        amount: values.get("amount"), issuer_establishment_id: values.get("issuer_establishment_id")
      }) }, true);
      setOneTimeOpen(false);
      onNotice(result.billing_status === "ready" ? "success" : "error", result.billing_status === "ready" ? "Item avulso validado e pronto para emissão." : "Item criado, mas bloqueado por dados fiscais pendentes no CRM.");
      await load(); await openItem(result.billing_item_id);
    } catch (error) { onNotice("error", error instanceof Error ? error.message : "Falha na emissão avulsa"); setLoading(false); }
  }

  return <section className="workspace billing-workspace">
    <header className="contracts-header">
      <div><p className="overline">FINANCEIRO · ETAPA 6</p><h1>Faturamento e NFS-e</h1><p>Obrigações determinísticas com emissão fiscal idempotente.</p><button className="one-time-button" type="button" onClick={() => { setOneTimeUnit(references?.business_units[0]?.id ?? ""); setOneTimeOpen(true); }}>+ Nova emissão avulsa</button></div>
      <form className="billing-generate" onSubmit={generate}>
        <label>Competência<input aria-label="Competência" type="month" required value={competence} onChange={(event) => setCompetence(event.target.value)} /></label>
        <label>Unidade<select aria-label="Unidade para geração" required value={unit} onChange={(event) => setUnit(event.target.value)}><option value="">Selecione</option>{references?.business_units.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
        <button className="primary" disabled={loading} type="submit">{loading ? "Processando…" : "Gerar competência"}</button>
      </form>
    </header>

    <section className="metrics billing-metrics">
      <article><span>VALOR PREVISTO</span><strong>{money(summary?.predicted_gross_amount ?? "0")}</strong><small>{summary?.ready_contracts ?? 0} prontos</small></article>
      <article><span>OBRIGAÇÕES</span><strong>{summary?.eligible_contracts ?? 0}</strong><small>{money(String(grossTotal))} conhecido</small></article>
      <article className={summary?.blocked_contracts ? "attention" : ""}><span>BLOQUEADOS</span><strong>{summary?.blocked_contracts ?? 0}</strong><small>{money(summary?.blocked_gross_amount ?? "0")}</small></article>
    </section>

    <div className="billing-filter-row">
      <label>Cliente<select value={customer} onChange={(event) => setCustomer(event.target.value)}><option value="">Todos</option>{references?.companies.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      <label>Status<select value={status} onChange={(event) => setStatus(event.target.value)}><option value="">Todos</option><option value="ready">Pronto</option><option value="blocked">Bloqueado</option><option value="requested">Solicitado</option><option value="completed">Concluído</option><option value="cancelled">Cancelado</option></select></label>
      <button type="button" onClick={() => void load()}>Atualizar</button>
    </div>

    <section className="billing-run-strip">
      <h2>Execuções da competência</h2>
      {runs.length ? runs.map((run) => <button key={run.id} type="button" onClick={() => void openRun(run.id)}><span>{run.business_unit_name}</span><strong>{statusLabel(run.status)}</strong><small>{run.metrics.ready ?? 0} prontos · {run.metrics.blocked ?? 0} bloqueados</small></button>) : <p className="muted">Nenhuma execução para os filtros.</p>}
    </section>

    <div className={`contract-table-shell ${loading ? "loading" : ""}`}>
      <table className="contract-table billing-table"><thead><tr><th>Cliente / contrato</th><th>Unidade</th><th>Emissor</th><th>Competência</th><th>Valor bruto</th><th>Status</th><th>Exceção</th><th /></tr></thead><tbody>
        {items.map((item) => <tr key={item.id}><td data-label="Cliente / origem"><strong>{item.customer_name}</strong><span>{item.contract_number} · {item.source_type.replaceAll("_", " ")}</span></td><td data-label="Unidade">{item.business_unit_name}</td><td data-label="Emissor">{item.issuer_name ?? "Indisponível"}</td><td data-label="Competência">{item.competence_month}</td><td data-label="Valor bruto">{money(item.gross_amount, item.currency ?? "BRL")}</td><td data-label="Status"><span className={`state-pill ${item.status}`}>{statusLabel(item.status)}</span></td><td data-label="Exceção"><small>{item.blocking_reason ?? "—"}</small></td><td><div className="fiscal-row-actions"><button type="button" onClick={() => void openItem(item.id)}>Inspecionar</button>{item.status === "ready" && <button className="issue" disabled={issuing === item.id} type="button" onClick={() => void emitItem(item)}>{issuing === item.id ? "Emitindo…" : "Emitir NFS-e"}</button>}</div></td></tr>)}
        {!items.length && <tr><td className="contract-empty" colSpan={8}>Nenhuma obrigação encontrada.</td></tr>}
      </tbody></table>
    </div>

    {selectedRun && <div className="overlay drawer-overlay" role="presentation" onMouseDown={() => setSelectedRun(null)}><aside className="drawer contract-drawer billing-drawer" onMouseDown={(event) => event.stopPropagation()}><header><div><p className="overline">EXECUÇÃO · {selectedRun.competence_month}</p><h2>{selectedRun.business_unit_name}</h2><p>{statusLabel(selectedRun.status)} · {selectedRun.operational_timezone}</p></div><button type="button" onClick={() => setSelectedRun(null)}>×</button></header><section><h3>Contratos considerados</h3><div className="billing-contract-list">{selectedRun.contracts.map((entry) => <article key={entry.contract_id}><span className={`state-pill ${entry.outcome}`}>{entry.outcome}</span><strong>{entry.customer_name}</strong><small>{entry.contract_number}</small>{entry.reason_detail && <p>{entry.reason_detail}</p>}</article>)}</div></section></aside></div>}

    {selectedItem && <div className="overlay drawer-overlay" role="presentation" onMouseDown={() => { setSelectedItem(null); setIssuance(null); }}><aside className="drawer contract-drawer billing-drawer" onMouseDown={(event) => event.stopPropagation()}><header><div><p className="overline">OBRIGAÇÃO · {selectedItem.competence_month}</p><h2>{selectedItem.customer_name}</h2><p>{selectedItem.contract_number} · {statusLabel(selectedItem.status)}</p></div><button type="button" onClick={() => { setSelectedItem(null); setIssuance(null); }}>×</button></header>{selectedItem.status === "ready" && <section className="issue-confirmation"><h3>Pronto para emissão</h3><dl><div><dt>Cliente</dt><dd>{selectedItem.customer_name}</dd></div><div><dt>Serviço</dt><dd>{selectedItem.contract_number}</dd></div><div><dt>Valor</dt><dd>{money(selectedItem.gross_amount, selectedItem.currency ?? "BRL")}</dd></div><div><dt>Referência</dt><dd>{selectedItem.competence_month}</dd></div><div><dt>Emissor</dt><dd>{selectedItem.issuer_name}</dd></div></dl><button className="primary" disabled={issuing === selectedItem.id} type="button" onClick={() => void emitItem(selectedItem)}>{issuing === selectedItem.id ? "Processando…" : "Emitir NFS-e"}</button></section>}{issuance && <section className="fiscal-result"><h3>{issuance.nfse_number ? `NFS-e ${issuance.nfse_number}` : "NFS-e"}</h3><dl className="fiscal-metadata"><div><dt>Status</dt><dd>{issuanceStatusLabel(issuance.status)}</dd></div><div><dt>Emissor</dt><dd>{issuance.issuer_name}</dd></div><div><dt>Número da NFS-e</dt><dd>{issuance.nfse_number ?? "Pendente"}</dd></div><div><dt>Número da DPS</dt><dd>{issuance.dps_number}</dd></div></dl>{issuance.access_key && <p className="hash-line">Chave de acesso · {issuance.access_key}</p>}{issuance.error_message && <p className="fiscal-error">{issuance.error_message}</p>}{["uncertain", "external_unavailable"].includes(issuance.status) && <button type="button" disabled={Boolean(issuing)} onClick={() => void reconcile()}>Consultar e reconciliar</button>}<div className="fiscal-documents">{issuance.documents.filter((document) => ["nfse_xml", "danfse_pdf"].includes(document.document_type)).map((document) => <button key={document.id} disabled={document.status !== "available"} type="button" onClick={() => void downloadDocument(document)}>{document.document_type === "nfse_xml" ? "Baixar XML" : "Baixar PDF"}</button>)}</div><details><summary>Tentativas auditadas</summary>{issuance.attempts.map((attempt) => <div className="timeline-item" key={attempt.attempt_number}><span>#{attempt.attempt_number}</span><strong>{attempt.operation}</strong><small>{attempt.outcome}</small></div>)}</details></section>}<section><h3>Snapshot imutável</h3><p className="hash-line">SHA-256 · {selectedItem.snapshot_sha256}</p><details><summary>Dados congelados</summary><pre>{JSON.stringify(selectedItem.snapshot, null, 2)}</pre></details></section><section><h3>Histórico e eventos</h3>{selectedItem.history.map((event) => <div className="timeline-item" key={`${event.kind}-${event.name}`}><span>{event.kind}</span><strong>{event.name}</strong><small>{event.status ?? "registrado"}</small></div>)}</section></aside></div>}

    {oneTimeOpen && references && <div className="overlay" role="presentation" onMouseDown={() => setOneTimeOpen(false)}><section className="panel one-time-panel" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}><header><div><p className="overline">FINANCEIRO · EMISSÃO AVULSA</p><h2>Nova emissão avulsa</h2><p>O cliente precisa existir no CRM.</p></div><button type="button" onClick={() => setOneTimeOpen(false)}>×</button></header><form onSubmit={createOneTime}>{(() => { const activeUnit = references.business_units.find((item) => item.id === oneTimeUnit) ?? references.business_units[0]; const allowedIssuer = references.fiscal_establishments.find((item) => item.id === activeUnit?.primary_establishment_id); return <><label>Cliente existente<select name="customer_company_id" required defaultValue=""><option value="" disabled>Selecione no CRM</option>{references.companies.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Unidade<select name="business_unit_id" required value={activeUnit?.id ?? ""} onChange={(event) => setOneTimeUnit(event.target.value)}>{references.business_units.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Serviço pontual<input name="service_name" required /></label><label>Descrição<textarea name="description" rows={3} required /></label><div className="form-grid"><label>Referência<input name="reference" required /></label><label>Data do serviço<input name="service_date" type="date" required defaultValue={new Date().toISOString().slice(0, 10)} /></label></div><div className="form-grid"><label>Valor<input name="amount" type="number" min=".01" step=".01" required /></label><label>Produto / serviço<select name="product_service_id"><option value="">Não vinculado</option>{references.products_services.filter((item) => item.business_unit_id === activeUnit?.id).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label></div><label>Emissor permitido<select value={allowedIssuer?.id ?? ""} disabled>{allowedIssuer && <option value={allowedIssuer.id}>{allowedIssuer.name}</option>}</select><input name="issuer_establishment_id" type="hidden" value={allowedIssuer?.id ?? ""} /></label><p className="form-help">Cliente ausente? Feche este fluxo, use “Novo registro → Empresa” e retorne ao Financeiro.</p></>; })()}<div className="panel-actions"><button type="button" onClick={() => setOneTimeOpen(false)}>Cancelar</button><button className="primary" disabled={loading} type="submit">{loading ? "Validando…" : "Gerar item faturável"}</button></div></form></section></div>}
  </section>;
}
