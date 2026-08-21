import type {
  AttentionItemMock,
  ContractMock,
  FinanceItemMock,
  OpportunityMock,
  TaskMock,
  UnitContext
} from "../components/types";

export const units: UnitContext[] = ["Grupo", "Unidade A", "Unidade B", "Unidade C"];

export const attentionItems: AttentionItemMock[] = [
  {
    id: "attention-1",
    title: "2 tarefas críticas vencem hoje",
    description: "Uma proposta e uma revisão contratual ainda aguardam responsável.",
    severity: "critical",
    actionLabel: "Revisar tarefas",
    module: "tasks"
  },
  {
    id: "attention-2",
    title: "1 obrigação precisa de revisão",
    description: "A competência demonstrativa de agosto contém um item bloqueado.",
    severity: "attention",
    actionLabel: "Ver exceção",
    module: "finance"
  },
  {
    id: "attention-3",
    title: "Oportunidade sem próxima ação",
    description: "Projeto Gama está em diagnóstico e precisa de um próximo passo.",
    severity: "info",
    actionLabel: "Abrir CRM",
    module: "crm"
  }
];

export const opportunities: OpportunityMock[] = [
  { id: "opp-01", title: "Expansão operacional", company: "Cliente Alfa", value: 68000, stage: "Qualificação", nextAction: "Confirmar escopo inicial", nextDate: "Hoje, 14:30", unit: "Unidade A", owner: "Marina" },
  { id: "opp-02", title: "Projeto Gama", company: "Empresa Beta", value: 124000, stage: "Diagnóstico", nextAction: "Definir próximo passo", nextDate: "Sem data", unit: "Unidade B", owner: "Caio" },
  { id: "opp-03", title: "Programa Horizonte", company: "Companhia Delta", value: 94000, stage: "Diagnóstico", nextAction: "Reunião de alinhamento", nextDate: "22 ago, 10:00", unit: "Unidade C", owner: "Lia" },
  { id: "opp-04", title: "Ciclo Atlas", company: "Grupo Épsilon", value: 156000, stage: "Proposta", nextAction: "Revisar proposta", nextDate: "Hoje, 16:00", unit: "Unidade A", owner: "Marina" },
  { id: "opp-05", title: "Frente Aurora", company: "Cliente Zeta", value: 83000, stage: "Proposta", nextAction: "Retorno comercial", nextDate: "25 ago", unit: "Unidade B", owner: "Caio" },
  { id: "opp-06", title: "Operação Nexo", company: "Empresa Ômega", value: 210000, stage: "Decisão", nextAction: "Aprovação executiva", nextDate: "23 ago", unit: "Unidade C", owner: "Lia" }
];

export const people = [
  { id: "person-01", name: "Ana Souza", role: "Diretora de Operações", company: "Cliente Alfa", email: "ana.souza@example.com", units: ["Unidade A", "Unidade B"] },
  { id: "person-02", name: "Bruno Lima", role: "Gestor de Projetos", company: "Empresa Beta", email: "bruno.lima@example.com", units: ["Unidade B"] },
  { id: "person-03", name: "Carla Mendes", role: "Diretora Financeira", company: "Companhia Delta", email: "carla.mendes@example.com", units: ["Unidade C"] },
  { id: "person-04", name: "Diego Alves", role: "Coordenador", company: "Grupo Épsilon", email: "diego.alves@example.com", units: ["Unidade A"] }
];

export const companies = [
  { id: "company-01", name: "Cliente Alfa", segment: "Serviços", city: "Cidade Exemplo", units: ["Unidade A", "Unidade B"], health: "Relacionamento ativo" },
  { id: "company-02", name: "Empresa Beta", segment: "Tecnologia", city: "Município Modelo", units: ["Unidade B"], health: "Próxima ação pendente" },
  { id: "company-03", name: "Companhia Delta", segment: "Indústria", city: "Vila Fictícia", units: ["Unidade C"], health: "Relacionamento ativo" },
  { id: "company-04", name: "Grupo Épsilon", segment: "Varejo", city: "Distrito Teste", units: ["Unidade A"], health: "Em negociação" }
];

export const contracts: ContractMock[] = [
  { id: "contract-01", number: "CT-1001", company: "Cliente Alfa", service: "Gestão operacional", value: 48000, unit: "Unidade A", administrative: "Ativo", temporal: "Atual", operational: "Vigente", issuer: "Entidade demonstrativa A", contact: "financeiro.alfa@example.com" },
  { id: "contract-02", number: "CT-1002", company: "Empresa Beta", service: "Projeto Gama", value: 72000, unit: "Unidade B", administrative: "Ativo", temporal: "Atual", operational: "Suspenso", issuer: "Entidade demonstrativa B", contact: "contato.beta@example.com" },
  { id: "contract-03", number: "CT-1003", company: "Companhia Delta", service: "Programa Horizonte", value: 96000, unit: "Unidade C", administrative: "Ativo", temporal: "Atual", operational: "Vigente", issuer: "Entidade demonstrativa C", contact: "financeiro.delta@example.com" },
  { id: "contract-04", number: "CT-1004", company: "Grupo Épsilon", service: "Ciclo Atlas", value: 54000, unit: "Unidade A", administrative: "Rascunho", temporal: "Futura", operational: "Vigente", issuer: "Entidade demonstrativa A", contact: "contato.epsilon@example.com" }
];

export const financeItems: FinanceItemMock[] = [
  { id: "fin-01", company: "Cliente Alfa", contract: "CT-1001", competence: "Ago 2026", value: 4000, unit: "Unidade A", status: "Pronto", note: "Item preparado para funcionalidade futura" },
  { id: "fin-02", company: "Empresa Beta", contract: "CT-1002", competence: "Ago 2026", value: 6000, unit: "Unidade B", status: "Bloqueado", note: "Revisão de domínio necessária" },
  { id: "fin-03", company: "Companhia Delta", contract: "CT-1003", competence: "Ago 2026", value: 8000, unit: "Unidade C", status: "Pronto", note: "Item preparado para funcionalidade futura" },
  { id: "fin-04", company: "Grupo Épsilon", contract: "CT-1004", competence: "Ago 2026", value: 4500, unit: "Unidade A", status: "Pronto", note: "Item preparado para funcionalidade futura" }
];

export const tasks: TaskMock[] = [
  { id: "task-01", title: "Revisar proposta do Ciclo Atlas", dueLabel: "Hoje, 16:00", bucket: "hoje", priority: "Crítica", owner: "Marina", context: "Oportunidade · Grupo Épsilon", unit: "Unidade A" },
  { id: "task-02", title: "Definir próximo passo do Projeto Gama", dueLabel: "Ontem, 17:00", bucket: "atrasadas", priority: "Alta", owner: "Caio", context: "Oportunidade · Empresa Beta", unit: "Unidade B" },
  { id: "task-03", title: "Confirmar escopo inicial", dueLabel: "Hoje, 14:30", bucket: "hoje", priority: "Alta", owner: "Marina", context: "Oportunidade · Cliente Alfa", unit: "Unidade A" },
  { id: "task-04", title: "Preparar reunião do Programa Horizonte", dueLabel: "22 ago, 10:00", bucket: "proximas", priority: "Média", owner: "Lia", context: "Empresa · Companhia Delta", unit: "Unidade C" },
  { id: "task-05", title: "Validar contato financeiro", dueLabel: "25 ago, 11:00", bucket: "proximas", priority: "Baixa", owner: "Caio", context: "Contrato · CT-1002", unit: "Unidade B" }
];

export const activities = [
  { date: "Hoje, 09:42", title: "Reunião de diagnóstico registrada", detail: "Projeto Gama · Bruno Lima", tone: "info" },
  { date: "Ontem, 17:18", title: "Proposta atualizada", detail: "Ciclo Atlas · Grupo Épsilon", tone: "success" },
  { date: "18 ago, 11:05", title: "Contato financeiro confirmado", detail: "Cliente Alfa · CT-1001", tone: "neutral" }
];

export const automationCards = [
  { title: "Fluxo de acompanhamento", description: "Exemplo conceitual de acompanhamento após reunião.", status: "Demonstração", tone: "neutral" },
  { title: "Conector de agenda", description: "Representação visual sem serviço externo conectado.", status: "Não conectado", tone: "attention" },
  { title: "Resumo semanal", description: "Modelo visual de execução, sem automação real.", status: "Somente visual", tone: "info" }
];
