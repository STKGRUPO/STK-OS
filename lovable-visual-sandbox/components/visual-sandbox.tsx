"use client";

import {
  type DragEvent,
  type ReactNode,
  useEffect,
  useMemo,
  useRef,
  useState
} from "react";

import {
  activities,
  attentionItems,
  automationCards,
  companies,
  contracts,
  financeItems,
  opportunities as opportunityFixtures,
  people,
  tasks as taskFixtures,
  units
} from "../mock-data/fixtures";
import type { ContractMock, FinanceItemMock, Screen, Severity, TaskMock, UnitContext } from "./types";

const navigation: { id: Screen; label: string; icon: string }[] = [
  { id: "home", label: "Início", icon: "⌂" },
  { id: "crm", label: "CRM", icon: "◇" },
  { id: "contracts", label: "Contratos", icon: "▤" },
  { id: "finance", label: "Financeiro", icon: "◫" },
  { id: "tasks", label: "Tarefas", icon: "✓" },
  { id: "automations", label: "Automações", icon: "⌁" }
];

const stageNames = ["Qualificação", "Diagnóstico", "Proposta", "Decisão"] as const;

function money(value: number) {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
    maximumFractionDigits: 0
  }).format(value);
}

function contextual<T extends { unit: Exclude<UnitContext, "Grupo"> }>(items: T[], unit: UnitContext) {
  return unit === "Grupo" ? items : items.filter((item) => item.unit === unit);
}

function StatusBadge({ children, tone = "neutral" }: { children: ReactNode; tone?: Severity | "ready" | "blocked" }) {
  return <span className={`status-badge ${tone}`}><span aria-hidden="true" />{children}</span>;
}

function Avatar({ name, size = "md" }: { name: string; size?: "sm" | "md" }) {
  const initials = name.split(" ").slice(0, 2).map((part) => part[0]).join("");
  return <span className={`avatar ${size}`}>{initials}</span>;
}

function PageHeader({ eyebrow, title, description, actions }: { eyebrow: string; title: string; description: string; actions?: ReactNode }) {
  return (
    <header className="page-header">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </header>
  );
}

function EmptyState({ icon = "○", title, description }: { icon?: string; title: string; description: string }) {
  return <div className="empty-state"><span aria-hidden="true">{icon}</span><strong>{title}</strong><p>{description}</p></div>;
}

function SectionTitle({ title, detail, action }: { title: string; detail?: string; action?: ReactNode }) {
  return <div className="section-title"><div><h2>{title}</h2>{detail && <p>{detail}</p>}</div>{action}</div>;
}

function HomeScreen({ onNavigate, unit }: { onNavigate: (screen: Screen) => void; unit: UnitContext }) {
  const relevantTasks = contextual(taskFixtures, unit).filter((task) => !task.done);
  const relevantOpportunities = contextual(opportunityFixtures, unit);
  const pipelineValue = relevantOpportunities.reduce((sum, item) => sum + item.value, 0);

  return (
    <div className="screen home-screen">
      <PageHeader
        eyebrow="QUINTA-FEIRA · 20 DE AGOSTO"
        title="Bom dia, Alex."
        description={unit === "Grupo" ? "Aqui está o que mais importa agora no Grupo." : `Aqui está o que mais importa agora em ${unit}.`}
        actions={<button className="subtle-button" onClick={() => onNavigate("tasks")}>Ver agenda <span>→</span></button>}
      />

      <section className="attention-section">
        <SectionTitle title="Precisa da sua atenção" detail="Exceções e decisões, em ordem de impacto." />
        <div className="attention-grid">
          {attentionItems.map((item, index) => (
            <article className={`attention-card ${item.severity}`} key={item.id}>
              <div className="attention-number">0{index + 1}</div>
              <StatusBadge tone={item.severity}>{item.severity === "critical" ? "Crítico" : item.severity === "attention" ? "Atenção" : "Contexto"}</StatusBadge>
              <h3>{item.title}</h3>
              <p>{item.description}</p>
              <button onClick={() => onNavigate(item.module)}>{item.actionLabel}<span>→</span></button>
            </article>
          ))}
        </div>
      </section>

      <div className="home-lower-grid">
        <section className="surface upcoming-panel">
          <SectionTitle title="Próximos 7 dias" detail={`${relevantTasks.length} prioridades no contexto atual`} action={<button className="text-button" onClick={() => onNavigate("tasks")}>Todas as tarefas</button>} />
          <div className="agenda-list">
            {relevantTasks.slice(0, 4).map((task, index) => (
              <article key={task.id}>
                <div className="agenda-date"><strong>{index < 2 ? "20" : index === 2 ? "22" : "25"}</strong><span>AGO</span></div>
                <div><strong>{task.title}</strong><span>{task.context}</span></div>
                <Avatar name={task.owner} size="sm" />
                <StatusBadge tone={task.priority === "Crítica" ? "critical" : task.priority === "Alta" ? "attention" : "neutral"}>{task.priority}</StatusBadge>
              </article>
            ))}
          </div>
        </section>

        <aside className="surface executive-panel">
          <SectionTitle title="Visão executiva" detail="Leitura rápida, sem ruído operacional." />
          <div className="executive-metrics">
            <article><span>Pipeline aberto</span><strong>{money(pipelineValue)}</strong><small>{relevantOpportunities.length} oportunidades</small></article>
            <article><span>Previsto no mês</span><strong>{money(contextual(financeItems, unit).reduce((sum, item) => sum + item.value, 0))}</strong><small>Valores fictícios</small></article>
            <article><span>Contratos vigentes</span><strong>{contextual(contracts, unit).filter((item) => item.operational === "Vigente").length}</strong><small>no contexto atual</small></article>
          </div>
          <div className="priority-note"><span>↗</span><div><strong>Prioridade do dia</strong><p>Concluir decisões comerciais antes de abrir novas frentes.</p></div></div>
        </aside>
      </div>
    </div>
  );
}

function CrmScreen({ unit, onOpenCompany, notify }: { unit: UnitContext; onOpenCompany: (id: string) => void; notify: (message: string) => void }) {
  const [tab, setTab] = useState<"kanban" | "people" | "companies" | "opportunities">("kanban");
  const [opportunities, setOpportunities] = useState(opportunityFixtures);
  const filtered = contextual(opportunities, unit);
  const tabs = [
    ["kanban", "Kanban"], ["people", "Pessoas"], ["companies", "Empresas"], ["opportunities", "Oportunidades"]
  ] as const;

  function drop(event: DragEvent<HTMLElement>, stage: typeof stageNames[number]) {
    const id = event.dataTransfer.getData("text/opportunity");
    setOpportunities((current) => current.map((item) => item.id === id ? { ...item, stage } : item));
    notify("Movimento visual aplicado somente nesta demonstração.");
  }

  return (
    <div className="screen">
      <PageHeader eyebrow="RELACIONAMENTOS" title="CRM" description="Pessoas, empresas e oportunidades em um contexto canônico." actions={<button className="primary-button" onClick={() => notify("Formulário visual pronto para customização no Lovable.")}>＋ Nova oportunidade</button>} />
      <div className="module-tabs" role="tablist" aria-label="Visualizações do CRM">
        {tabs.map(([id, label]) => <button role="tab" aria-selected={tab === id} className={tab === id ? "active" : ""} key={id} onClick={() => setTab(id)}>{label}</button>)}
      </div>

      {tab === "kanban" && <section className="kanban-board" aria-label="Pipeline comercial">
        {stageNames.map((stage, index) => {
          const cards = filtered.filter((item) => item.stage === stage);
          return <article className="kanban-column" key={stage} onDragOver={(event) => event.preventDefault()} onDrop={(event) => drop(event, stage)}>
            <header><span>0{index + 1}</span><strong>{stage}</strong><small>{cards.length}</small></header>
            <div className="kanban-cards">
              {cards.map((item) => <button className="opportunity-card" draggable key={item.id} onDragStart={(event) => event.dataTransfer.setData("text/opportunity", item.id)} onClick={() => notify(`${item.title}: drawer visual preparado para evolução.`)}>
                <div><StatusBadge tone="neutral">{item.unit}</StatusBadge><span className="card-menu">•••</span></div>
                <strong>{item.title}</strong><p>{item.company}</p><b>{money(item.value)}</b>
                <footer><span>→ {item.nextAction}</span><small>{item.nextDate}</small></footer>
              </button>)}
              {!cards.length && <div className="empty-column">Solte uma oportunidade aqui</div>}
            </div>
          </article>;
        })}
      </section>}

      {tab === "people" && <section className="surface data-surface"><DirectoryToolbar label="pessoas" /><div className="directory-grid">{people.map((person) => <button className="directory-card" key={person.id} onClick={() => notify(`Visão 360° de ${person.name} disponível como padrão visual.`)}><Avatar name={person.name} /><div><strong>{person.name}</strong><span>{person.role}</span><small>{person.company} · {person.email}</small></div><span>→</span></button>)}</div></section>}
      {tab === "companies" && <section className="surface data-surface"><DirectoryToolbar label="empresas" /><div className="company-table table-like">{companies.map((company) => <button key={company.id} onClick={() => onOpenCompany(company.id)}><span className="table-main"><span className="company-monogram">{company.name[0]}</span><span><strong>{company.name}</strong><small>{company.segment} · {company.city}</small></span></span><span>{company.units.join(" · ")}</span><StatusBadge tone={company.health.includes("pendente") ? "attention" : "success"}>{company.health}</StatusBadge><span>→</span></button>)}</div></section>}
      {tab === "opportunities" && <section className="surface data-surface"><DirectoryToolbar label="oportunidades" /><div className="table-like opportunity-table">{filtered.map((item) => <button key={item.id} onClick={() => notify(`${item.title}: detalhe visual selecionado.`)}><span className="table-main"><span><strong>{item.title}</strong><small>{item.company}</small></span></span><StatusBadge tone="info">{item.stage}</StatusBadge><span>{money(item.value)}</span><span>{item.owner}</span><span>→</span></button>)}</div></section>}
    </div>
  );
}

function DirectoryToolbar({ label }: { label: string }) {
  return <div className="directory-toolbar"><div><strong>Todos os registros</strong><span>{label} sintéticas para demonstração</span></div><label className="inline-search"><span>⌕</span><input aria-label={`Filtrar ${label}`} placeholder={`Filtrar ${label}...`} /></label><button className="outline-button">Filtros</button></div>;
}

function ContractsScreen({ unit, onOpen, notify }: { unit: UnitContext; onOpen: (contract: ContractMock) => void; notify: (message: string) => void }) {
  const filtered = contextual(contracts, unit);
  return <div className="screen">
    <PageHeader eyebrow="BASE CANÔNICA" title="Contratos" description="Identidade estável, configuração versionada e história preservada." actions={<button className="primary-button" onClick={() => notify("Criação visual iniciada; nenhum contrato real será gravado.")}>＋ Novo contrato</button>} />
    <section className="compact-metrics">
      <article><span>Vigentes</span><strong>{filtered.filter((item) => item.operational === "Vigente").length}</strong><small>operação atual</small></article>
      <article><span>Versões futuras</span><strong>{filtered.filter((item) => item.temporal === "Futura").length}</strong><small>alterações planejadas</small></article>
      <article><span>Pedem atenção</span><strong>{filtered.filter((item) => item.operational === "Suspenso").length}</strong><small>suspensos</small></article>
    </section>
    <section className="surface data-surface">
      <DirectoryToolbar label="contratos" />
      <div className="table-like contracts-table">
        <div className="table-head"><span>Contrato / cliente</span><span>Unidade</span><span>Configuração</span><span>Valor</span><span>Situação</span><span /></div>
        {filtered.map((contract) => <button key={contract.id} onClick={() => onOpen(contract)}>
          <span className="table-main"><span><strong>{contract.number}</strong><small>{contract.company} · {contract.service}</small></span></span>
          <span>{contract.unit}</span><span>Versão 2 · {contract.temporal}</span><strong>{money(contract.value)}</strong><StatusBadge tone={contract.operational === "Suspenso" ? "attention" : "success"}>{contract.operational}</StatusBadge><span>→</span>
        </button>)}
      </div>
    </section>
  </div>;
}

function FinanceScreen({ unit, onOpen, onConfirm }: { unit: UnitContext; onOpen: (item: FinanceItemMock) => void; onConfirm: () => void }) {
  const filtered = contextual(financeItems, unit);
  const ready = filtered.filter((item) => item.status === "Pronto");
  const blocked = filtered.filter((item) => item.status === "Bloqueado");
  return <div className="screen">
    <PageHeader eyebrow="VISÃO EXECUTIVA" title="Financeiro" description="Competência, previsão e exceções com dados exclusivamente sintéticos." actions={<div className="action-cluster"><select aria-label="Competência"><option>Agosto 2026</option><option>Julho 2026</option></select><button className="primary-button" onClick={onConfirm}>Gerar competência</button></div>} />
    <section className="finance-hero surface">
      <div className="finance-total"><span>Faturamento previsto</span><strong>{money(filtered.reduce((sum, item) => sum + item.value, 0))}</strong><small>Competência Ago 2026 · valores fictícios</small></div>
      <div className="finance-chart" aria-label="Distribuição visual por unidade">
        <div style={{ height: "48%" }}><span>A</span></div><div style={{ height: "72%" }}><span>B</span></div><div style={{ height: "88%" }}><span>C</span></div>
      </div>
      <div className="finance-breakdown"><article><StatusBadge tone="success">Prontos</StatusBadge><strong>{ready.length}</strong><span>{money(ready.reduce((sum, item) => sum + item.value, 0))}</span></article><article><StatusBadge tone="critical">Bloqueados</StatusBadge><strong>{blocked.length}</strong><span>{money(blocked.reduce((sum, item) => sum + item.value, 0))}</span></article></div>
    </section>
    <section className="surface data-surface">
      <SectionTitle title="Obrigações da competência" detail="Pronto significa íntegro para uma etapa futura; não significa nota emitida." action={<button className="outline-button">Filtros</button>} />
      <div className="table-like finance-table">
        <div className="table-head"><span>Cliente / contrato</span><span>Unidade</span><span>Competência</span><span>Valor bruto</span><span>Estado</span><span /></div>
        {filtered.map((item) => <button key={item.id} onClick={() => onOpen(item)}><span className="table-main"><span><strong>{item.company}</strong><small>{item.contract}</small></span></span><span>{item.unit}</span><span>{item.competence}</span><strong>{money(item.value)}</strong><StatusBadge tone={item.status === "Bloqueado" ? "blocked" : "ready"}>{item.status}</StatusBadge><span>→</span></button>)}
      </div>
    </section>
  </div>;
}

function TasksScreen({ unit }: { unit: UnitContext }) {
  const [tasks, setTasks] = useState(taskFixtures);
  const [filter, setFilter] = useState<"todas" | TaskMock["bucket"]>("todas");
  const visible = contextual(tasks, unit).filter((task) => filter === "todas" || task.bucket === filter);
  const counts = useMemo(() => ({ atrasadas: contextual(tasks, unit).filter((task) => task.bucket === "atrasadas" && !task.done).length, hoje: contextual(tasks, unit).filter((task) => task.bucket === "hoje" && !task.done).length, proximas: contextual(tasks, unit).filter((task) => task.bucket === "proximas" && !task.done).length }), [tasks, unit]);
  return <div className="screen">
    <PageHeader eyebrow="TO-DO OPERACIONAL" title="Minhas tarefas" description="Prioridades com responsável e vínculo contextual sempre visíveis." actions={<button className="primary-button">＋ Nova tarefa</button>} />
    <div className="task-layout">
      <aside className="task-filters surface">
        {(["todas", "hoje", "atrasadas", "proximas"] as const).map((id) => <button className={filter === id ? "active" : ""} key={id} onClick={() => setFilter(id)}><span>{id === "todas" ? "Todas" : id === "proximas" ? "Próximas" : id[0].toUpperCase() + id.slice(1)}</span><small>{id === "todas" ? contextual(tasks, unit).filter((task) => !task.done).length : counts[id]}</small></button>)}
      </aside>
      <section className="surface task-list">
        <SectionTitle title={filter === "todas" ? "Todas as tarefas" : filter === "proximas" ? "Próximas" : filter[0].toUpperCase() + filter.slice(1)} detail={`${visible.filter((task) => !task.done).length} pendentes no contexto atual`} />
        {visible.map((task) => <article className={task.done ? "done" : ""} key={task.id}>
          <button className="task-check" aria-label={task.done ? "Reabrir tarefa" : "Concluir tarefa"} onClick={() => setTasks((current) => current.map((item) => item.id === task.id ? { ...item, done: !item.done } : item))}>{task.done ? "✓" : ""}</button>
          <div><strong>{task.title}</strong><span>{task.context} · {task.unit}</span></div>
          <span className="task-due">{task.dueLabel}</span><Avatar name={task.owner} size="sm" /><StatusBadge tone={task.priority === "Crítica" ? "critical" : task.priority === "Alta" ? "attention" : "neutral"}>{task.priority}</StatusBadge><button className="row-more" aria-label="Mais opções">•••</button>
        </article>)}
        {!visible.length && <EmptyState title="Nada por aqui" description="Não há tarefas sintéticas para este filtro e contexto." />}
      </section>
    </div>
  </div>;
}

function AutomationsScreen() {
  const [tab, setTab] = useState("Fluxos");
  return <div className="screen">
    <PageHeader eyebrow="EXPERIÊNCIA CONCEITUAL" title="Automações" description="Estrutura visual para fluxos, integrações, execuções e saúde, sem funcionalidade real." actions={<StatusBadge tone="info">future/mock</StatusBadge>} />
    <div className="module-tabs" role="tablist" aria-label="Áreas de automações">{["Fluxos", "Integrações", "Execuções", "Saúde"].map((item) => <button className={tab === item ? "active" : ""} key={item} onClick={() => setTab(item)}>{item}</button>)}</div>
    {tab === "Fluxos" ? <div className="automation-grid">{automationCards.map((card) => <article className="surface automation-card" key={card.title}><div className="automation-icon">⌁</div><StatusBadge tone={card.tone as Severity}>{card.status}</StatusBadge><h3>{card.title}</h3><p>{card.description}</p><button>Ver composição visual <span>→</span></button></article>)}</div> : <section className="surface automation-empty"><EmptyState icon="⌁" title={`${tab} ainda não possui fonte operacional`} description="Esta área demonstra apenas hierarquia, estados vazios e acabamento visual. Nenhuma conexão está ativa." /><div className="future-note"><StatusBadge tone="info">future/mock</StatusBadge><p>O Lovable pode refinar layout e componentes, mas não deve criar serviços, conexões ou persistência.</p></div></section>}
  </div>;
}

function CompanyDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const company = companies.find((item) => item.id === id) ?? companies[0];
  const related = opportunityFixtures.filter((item) => item.company === company.name);
  return <Drawer onClose={onClose} eyebrow="CLIENTE 360°" title={company.name} subtitle={`${company.segment} · ${company.city}`}>
    <div className="drawer-summary"><article><span>Relacionamento</span><strong>{company.health}</strong></article><article><span>Contextos</span><strong>{company.units.join(" · ")}</strong></article><article><span>Oportunidades</span><strong>{related.length}</strong></article></div>
    <section><SectionTitle title="Visão geral" detail="Contexto comercial sintético e consolidado." /><div className="contact-card"><Avatar name="Ana Souza" /><div><strong>Contato principal</strong><span>ana.souza@example.com</span></div><button>Ver pessoa →</button></div></section>
    <section><SectionTitle title="Oportunidades" />{related.length ? related.map((item) => <div className="drawer-row" key={item.id}><div><strong>{item.title}</strong><span>{item.stage} · {item.nextAction}</span></div><strong>{money(item.value)}</strong></div>) : <EmptyState title="Sem oportunidades" description="Nenhuma oportunidade sintética vinculada." />}</section>
    <section><SectionTitle title="Histórico e atividades" />{activities.map((activity) => <div className="timeline-row" key={activity.title}><span className={`timeline-dot ${activity.tone}`} /><time>{activity.date}</time><div><strong>{activity.title}</strong><span>{activity.detail}</span></div></div>)}</section>
  </Drawer>;
}

function ContractDrawer({ contract, onClose }: { contract: ContractMock; onClose: () => void }) {
  return <Drawer onClose={onClose} eyebrow="CONTRATO" title={contract.number} subtitle={`${contract.company} · ${contract.unit}`}>
    <div className="drawer-badges"><StatusBadge tone="success">Administrativo · {contract.administrative}</StatusBadge><StatusBadge tone="info">Temporal · {contract.temporal}</StatusBadge><StatusBadge tone={contract.operational === "Suspenso" ? "attention" : "success"}>Operacional · {contract.operational}</StatusBadge></div>
    <div className="drawer-summary"><article><span>Valor contratual</span><strong>{money(contract.value)}</strong></article><article><span>Emissor</span><strong>{contract.issuer}</strong></article><article><span>Contato financeiro</span><strong>{contract.contact}</strong></article></div>
    <section><SectionTitle title="Versões" detail="Atual, histórica e futura permanecem separadas." /><div className="version-stack"><article className="current"><StatusBadge tone="success">Atual</StatusBadge><strong>Versão 2</strong><span>01 jul 2026 — vigente</span><p>{contract.service} · {money(contract.value)}</p></article><article><StatusBadge tone="neutral">Histórica</StatusBadge><strong>Versão 1</strong><span>01 jan — 30 jun 2026</span><p>Configuração inicial preservada</p></article><article><StatusBadge tone="info">Futura</StatusBadge><strong>Versão 3</strong><span>Agendada para 01 jan 2027</span><p>Revisão anual planejada</p></article></div></section>
    <section><SectionTitle title="Serviços e contatos" /><div className="drawer-row"><div><strong>{contract.service}</strong><span>Serviço ativo na versão atual</span></div><StatusBadge tone="success">Ativo</StatusBadge></div><div className="drawer-row"><div><strong>{contract.contact}</strong><span>Contato financeiro principal</span></div><StatusBadge tone="neutral">E-mail</StatusBadge></div></section>
    <section><SectionTitle title="Eventos" /><div className="timeline-row"><span className="timeline-dot success" /><time>01 jul</time><div><strong>Nova versão vigente</strong><span>Alteração contratual registrada visualmente</span></div></div><div className="timeline-row"><span className="timeline-dot neutral" /><time>01 jan</time><div><strong>Contrato iniciado</strong><span>Identidade e versão inicial</span></div></div></section>
  </Drawer>;
}

function FinanceDrawer({ item, onClose }: { item: FinanceItemMock; onClose: () => void }) {
  return <Drawer onClose={onClose} eyebrow="DETALHE DA OBRIGAÇÃO" title={item.company} subtitle={`${item.contract} · ${item.competence}`}>
    <div className="drawer-badges"><StatusBadge tone={item.status === "Bloqueado" ? "blocked" : "ready"}>{item.status}</StatusBadge><StatusBadge tone="neutral">Dados fictícios</StatusBadge></div>
    <div className="drawer-summary"><article><span>Valor bruto</span><strong>{money(item.value)}</strong></article><article><span>Unidade</span><strong>{item.unit}</strong></article><article><span>Competência</span><strong>{item.competence}</strong></article></div>
    {item.status === "Bloqueado" && <div className="exception-box"><StatusBadge tone="critical">Exceção</StatusBadge><strong>Revisão necessária</strong><p>{item.note}. Nenhuma operação fiscal foi iniciada.</p></div>}
    <section><SectionTitle title="Registro visual" detail="Representação reduzida; não reproduz modelos internos." /><div className="snapshot-grid"><span><small>Cliente</small>{item.company}</span><span><small>Contrato</small>{item.contract}</span><span><small>Competência</small>{item.competence}</span><span><small>Valor</small>{money(item.value)}</span></div></section>
    <section><SectionTitle title="Histórico" /><div className="timeline-row"><span className={`timeline-dot ${item.status === "Bloqueado" ? "attention" : "success"}`} /><time>20 ago</time><div><strong>Obrigação {item.status.toLowerCase()}</strong><span>{item.note}</span></div></div><div className="timeline-row"><span className="timeline-dot neutral" /><time>20 ago</time><div><strong>Competência demonstrativa preparada</strong><span>Evento somente visual, sem gravação</span></div></div></section>
  </Drawer>;
}

function Drawer({ onClose, eyebrow, title, subtitle, children }: { onClose: () => void; eyebrow: string; title: string; subtitle: string; children: ReactNode }) {
  return <div className="overlay" role="presentation" onMouseDown={onClose}><aside className="drawer" role="dialog" aria-modal="true" aria-label={title} onMouseDown={(event) => event.stopPropagation()}><header><div><p className="eyebrow">{eyebrow}</p><h2>{title}</h2><p>{subtitle}</p></div><button onClick={onClose} aria-label="Fechar painel">×</button></header><div className="drawer-body">{children}</div></aside></div>;
}

function ConfirmDialog({ onClose, onSuccess }: { onClose: () => void; onSuccess: () => void }) {
  return <div className="overlay centered" role="presentation" onMouseDown={onClose}><section className="confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title" onMouseDown={(event) => event.stopPropagation()}><div className="confirm-icon">!</div><p className="eyebrow">AÇÃO SENSÍVEL · DEMONSTRAÇÃO</p><h2 id="confirm-title">Gerar competência de agosto?</h2><p>Este fluxo existe apenas para demonstrar confirmação visual. Ele não acessa serviços, não calcula valores e não grava dados.</p><dl><div><dt>Contexto</dt><dd>Grupo</dd></div><div><dt>Competência</dt><dd>Agosto 2026</dd></div><div><dt>Efeito real</dt><dd>Nenhum</dd></div></dl><div className="dialog-actions"><button className="outline-button" onClick={onClose}>Cancelar</button><button className="danger-button" onClick={onSuccess}>Confirmar demonstração</button></div></section></div>;
}

function CommandPalette({ open, onClose, onNavigate }: { open: boolean; onClose: () => void; onNavigate: (screen: Screen) => void }) {
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => { if (open) requestAnimationFrame(() => inputRef.current?.focus()); }, [open]);
  if (!open) return null;
  const normalized = query.trim().toLowerCase();
  const special = normalized.includes("carregando") ? "loading" : normalized.includes("vazio") ? "empty" : normalized.includes("erro") ? "error" : normalized.includes("permiss") ? "denied" : normalized.includes("sucesso") ? "success" : null;
  const results = [
    ...navigation.map((item) => ({ id: item.id, title: item.label, detail: "Ir para módulo", icon: item.icon, screen: item.id })),
    ...companies.map((item) => ({ id: item.id, title: item.name, detail: "Empresa · CRM", icon: "E", screen: "crm" as Screen })),
    ...people.map((item) => ({ id: item.id, title: item.name, detail: `${item.role} · CRM`, icon: "P", screen: "crm" as Screen }))
  ].filter((item) => !normalized || `${item.title} ${item.detail}`.toLowerCase().includes(normalized));
  return <div className="command-overlay" role="presentation" onMouseDown={onClose}><section className="command-palette" role="dialog" aria-modal="true" aria-label="Comando universal" onMouseDown={(event) => event.stopPropagation()}>
    <div className="command-input"><span>⌕</span><input ref={inputRef} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Buscar, perguntar ou comandar o STK OS..." /><kbd>ESC</kbd></div>
    <div className="command-content">
      {special === "loading" && <div className="command-state"><span className="spinner" /><strong>Buscando no contexto visual…</strong><p>Estado de carregamento demonstrativo.</p></div>}
      {special === "empty" && <EmptyState title="Nenhum resultado" description="Tente outro termo ou navegue por um dos módulos." />}
      {special === "error" && <div className="command-state error"><span>!</span><strong>Não foi possível concluir</strong><p>Estado de erro demonstrativo. Tente novamente.</p><button onClick={() => setQuery("")}>Tentar novamente</button></div>}
      {special === "denied" && <div className="command-state denied"><span>⊘</span><strong>Permissão necessária</strong><p>Você não possui acesso para esta ação demonstrativa.</p><button onClick={onClose}>Entendi</button></div>}
      {special === "success" && <div className="command-state success"><span>✓</span><strong>Ação visual concluída</strong><p>Nenhum comando real foi executado.</p><button onClick={onClose}>Fechar</button></div>}
      {!special && <><div className="command-label">{normalized ? "RESULTADOS" : "NAVEGAÇÃO RÁPIDA"}<span>{results.length}</span></div><div className="command-results">{results.slice(0, 8).map((item) => <button key={item.id} onClick={() => { onNavigate(item.screen); onClose(); }}><span className="result-symbol">{item.icon}</span><span><strong>{item.title}</strong><small>{item.detail}</small></span><kbd>↵</kbd></button>)}{!results.length && <EmptyState title="Nenhum resultado" description="Use um nome sintético ou o nome de um módulo." />}</div></>}
    </div>
    <footer><span><kbd>↑</kbd><kbd>↓</kbd> navegar</span><span><kbd>↵</kbd> abrir</span><span>Digite “erro”, “vazio”, “permissão”, “sucesso” ou “carregando” para ver estados</span></footer>
  </section></div>;
}

export function VisualSandbox() {
  const [screen, setScreen] = useState<Screen>("home");
  const [unit, setUnit] = useState<UnitContext>("Grupo");
  const [commandOpen, setCommandOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [selectedCompany, setSelectedCompany] = useState<string | null>(null);
  const [selectedContract, setSelectedContract] = useState<ContractMock | null>(null);
  const [selectedFinance, setSelectedFinance] = useState<FinanceItemMock | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [toast, setToast] = useState("");

  useEffect(() => {
    function shortcut(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); setCommandOpen((current) => !current); }
      if (event.key === "Escape") { setCommandOpen(false); setSelectedCompany(null); setSelectedContract(null); setSelectedFinance(null); setConfirmOpen(false); }
    }
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  }, []);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(""), 3200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  function navigate(next: Screen) { setScreen(next); setMobileOpen(false); window.scrollTo({ top: 0, behavior: "smooth" }); }
  const activeLabel = navigation.find((item) => item.id === screen)?.label ?? "Início";

  return <main className="app-shell">
    <aside className={`sidebar ${mobileOpen ? "mobile-open" : ""}`}>
      <div className="brand"><span>STK</span><div><strong>STK OS</strong><small>Visual sandbox</small></div></div>
      <nav aria-label="Navegação principal">{navigation.map((item) => <button className={screen === item.id ? "active" : ""} key={item.id} onClick={() => navigate(item.id)}><span className="nav-icon">{item.icon}</span><span>{item.label}</span>{screen === item.id && <i />}</button>)}</nav>
      <div className="sidebar-principle"><span>PRINCÍPIO</span><p>O sistema sabe tudo.<br />A tela mostra só o que importa agora.</p></div>
      <div className="profile"><Avatar name="Alex Demo" /><div><strong>Alex Demo</strong><span>Ambiente visual</span></div><button aria-label="Opções do perfil">•••</button></div>
    </aside>

    <section className="main-area">
      <header className="global-bar">
        <button className="mobile-menu" aria-label="Abrir menu" onClick={() => setMobileOpen((current) => !current)}>☰</button>
        <div className="breadcrumb"><span>STK OS</span><b>/</b><strong>{activeLabel}</strong></div>
        <button className="command-trigger" onClick={() => setCommandOpen(true)}><span>⌕</span><span>Buscar, perguntar ou comandar o STK OS...</span><kbd>Ctrl K</kbd><i aria-hidden="true">◉</i></button>
        <label className="unit-switcher"><span>Contexto</span><select value={unit} onChange={(event) => setUnit(event.target.value as UnitContext)}>{units.map((item) => <option key={item}>{item}</option>)}</select></label>
        <button className="notification-button" aria-label="Notificações">○<span /></button>
      </header>

      <div className="content-area">
        {screen === "home" && <HomeScreen onNavigate={navigate} unit={unit} />}
        {screen === "crm" && <CrmScreen unit={unit} onOpenCompany={setSelectedCompany} notify={setToast} />}
        {screen === "contracts" && <ContractsScreen unit={unit} onOpen={setSelectedContract} notify={setToast} />}
        {screen === "finance" && <FinanceScreen unit={unit} onOpen={setSelectedFinance} onConfirm={() => setConfirmOpen(true)} />}
        {screen === "tasks" && <TasksScreen unit={unit} />}
        {screen === "automations" && <AutomationsScreen />}
      </div>
    </section>

    <CommandPalette key={commandOpen ? "open" : "closed"} open={commandOpen} onClose={() => setCommandOpen(false)} onNavigate={navigate} />
    {selectedCompany && <CompanyDrawer id={selectedCompany} onClose={() => setSelectedCompany(null)} />}
    {selectedContract && <ContractDrawer contract={selectedContract} onClose={() => setSelectedContract(null)} />}
    {selectedFinance && <FinanceDrawer item={selectedFinance} onClose={() => setSelectedFinance(null)} />}
    {confirmOpen && <ConfirmDialog onClose={() => setConfirmOpen(false)} onSuccess={() => { setConfirmOpen(false); setToast("Demonstração concluída. Nenhum dado foi gravado."); }} />}
    {toast && <button className="toast" onClick={() => setToast("")}><span>✓</span>{toast}<b>×</b></button>}
    <div className="sandbox-flag">SANDBOX VISUAL · DADOS FICTÍCIOS</div>
  </main>;
}
