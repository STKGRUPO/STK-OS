export type Screen = "home" | "crm" | "contracts" | "finance" | "tasks" | "automations";
export type UnitContext = "Grupo" | "Unidade A" | "Unidade B" | "Unidade C";
export type Severity = "info" | "attention" | "critical" | "success" | "neutral";

export type AttentionItemMock = {
  id: string;
  title: string;
  description: string;
  severity: Exclude<Severity, "success" | "neutral">;
  actionLabel?: string;
  module: Screen;
};

export type TaskMock = {
  id: string;
  title: string;
  dueLabel: string;
  bucket: "atrasadas" | "hoje" | "proximas";
  priority: "Baixa" | "Média" | "Alta" | "Crítica";
  owner: string;
  context: string;
  unit: Exclude<UnitContext, "Grupo">;
  done?: boolean;
};

export type OpportunityMock = {
  id: string;
  title: string;
  company: string;
  value: number;
  stage: "Qualificação" | "Diagnóstico" | "Proposta" | "Decisão";
  nextAction: string;
  nextDate: string;
  unit: Exclude<UnitContext, "Grupo">;
  owner: string;
};

export type ContractMock = {
  id: string;
  number: string;
  company: string;
  service: string;
  value: number;
  unit: Exclude<UnitContext, "Grupo">;
  administrative: "Ativo" | "Rascunho" | "Arquivado";
  temporal: "Atual" | "Futura" | "Histórica";
  operational: "Vigente" | "Suspenso" | "Encerrado";
  issuer: string;
  contact: string;
};

export type FinanceItemMock = {
  id: string;
  company: string;
  contract: string;
  competence: string;
  value: number;
  unit: Exclude<UnitContext, "Grupo">;
  status: "Pronto" | "Bloqueado";
  note: string;
};
