# Frontend Handoff — STK OS V1 → Lovable

**Status do backend considerado:** Etapas 0 a 5 concluídas e aprovadas  
**Data de corte:** 20 de agosto de 2026  
**Fonte contratual da API:** `contracts/api/openapi.json`  
**Objetivo:** orientar a implementação visual do frontend sem recriar ou antecipar o backend.

## 1. Escopo e fonte de verdade

O STK OS é a plataforma operacional central do Grupo STK. O backend FastAPI e o PostgreSQL existentes são os donos dos dados, das regras, dos estados, da autorização, das invariantes, da idempotência e da auditoria. O Lovable será usado apenas como acelerador de frontend e UX.

```text
Lovable / Frontend
        ↓ HTTPS / JSON
     STK OS API
        ↓
 FastAPI / PostgreSQL
```

Ordem de autoridade para a implementação:

1. `contracts/api/openapi.json`, para rotas e schemas HTTP;
2. routers e schemas em `apps/api/src/stk_os`, para autorização e comportamento;
3. migrations, ADRs e documentação de domínio, para invariantes e semântica;
4. este handoff, para composição das telas e limites do frontend.

O frontend:

- nunca acessa PostgreSQL diretamente;
- nunca implementa regra financeira, elegibilidade contratual ou cálculo fiscal;
- nunca escolhe o estabelecimento emissor;
- nunca cria, altera ou recalcula snapshots e hashes;
- nunca trata logs do n8n como verdade do negócio;
- nunca armazena secrets, client secrets ou credenciais de service account;
- nunca assume um estado de domínio que não tenha vindo da API;
- envia valores monetários como valores decimais compatíveis com o contrato e exibe os valores decimais devolvidos pela API, sem usar ponto flutuante para decisões;
- considera `America/Sao_Paulo` o timezone operacional atual para competência, sem substituir essa regra pelo timezone do navegador.

## 2. Baseline técnico existente

### Backend

- FastAPI, prefixo transacional `/api/v1`;
- PostgreSQL via SQLAlchemy;
- OpenAPI versionado no repositório;
- JWT Bearer curto, atualmente emitido por autenticação local;
- capabilities persistidas e, em contratos/faturamento, escopo de unidade por papel;
- auditoria e outbox transacionais; inbox deduplicada para eventos externos;
- `X-Correlation-ID` aceito/devolvido para rastreabilidade;
- CORS local atualmente limitado a `http://127.0.0.1:3000` e `http://localhost:3000`.

### Frontend atual

- Next.js 16, React 19 e TypeScript;
- uma única rota real, `/`, implementada em `apps/web/app/page.tsx`;
- login local, token mantido apenas em estado React, sem refresh token;
- workspaces internos para CRM, Contratos e Faturamento;
- CRM com Kanban, busca, cadastros, atividades, tarefas vinculadas e visão 360°;
- Contratos com lista, filtros, criação, versionamento, consulta temporal e eventos operacionais;
- Faturamento com geração de competência, resumo, runs, items, bloqueios, snapshot e histórico;
- não há roteamento dedicado para os módulos, AppShell definitivo, Home executiva, Ctrl+K, página geral de tarefas ou página de automações.

O frontend atual é uma prova funcional. O Lovable pode substituir sua composição visual e criar as rotas recomendadas, mas deve preservar os contratos HTTP e não copiar regras de domínio para o browser.

## 3. Arquitetura de integração do frontend

Centralizar chamadas em um cliente tipado da STK OS API, configurado por URL pública **não secreta**, por exemplo `NEXT_PUBLIC_STK_API_URL`. Nenhuma outra variável `NEXT_PUBLIC_*` pode conter senha, JWT secret, client secret, chave bancária, certificado ou credencial de integração.

Requisitos do cliente HTTP:

- acrescentar `Authorization: Bearer <access_token>` somente a rotas protegidas;
- enviar `Content-Type: application/json` em payloads JSON;
- gerar uma `Idempotency-Key` UUID nova para cada nova intenção de escrita e reutilizá-la apenas ao repetir exatamente a mesma intenção após falha de transporte;
- opcionalmente enviar `X-Correlation-ID` UUID e sempre preservar/expor o valor devolvido em diagnósticos;
- usar `cache: no-store` para dados operacionais mutáveis;
- não fazer retry automático de mutações com uma nova chave;
- tratar `Decimal` devolvido como string e datas civis (`date`) separadamente de instantes (`date-time`);
- cancelar requisições obsoletas ao trocar de contexto/filtro;
- nunca aplicar optimistic update a uma transição crítica sem rollback visual e confirmação da resposta do backend.

## 4. Navegação e rotas recomendadas

A sidebar principal aprovada é:

1. Início
2. CRM
3. Contratos
4. Financeiro
5. Tarefas
6. Automações

MR, STK Lab e Stelli não são módulos da sidebar. São opções do `UnitSwitcher`, ao lado de Grupo STK.

| Rota sugerida | Tela | Situação da API | Implementação permitida agora |
|---|---|---|---|
| `/` | Início | Parcial; não há endpoint agregador de Home | Montar apenas dados deriváveis das consultas existentes; marcar blocos sem fonte como indisponíveis, não como zero |
| `/crm` | CRM / Kanban | Atual | Kanban por pipeline, filtros por contexto, busca e ações autorizadas |
| `/crm/pessoas` | Pessoas | Atual | Lista/busca, criação, edição e acesso à visão 360° |
| `/crm/empresas` | Empresas | Atual | Lista/busca, criação, edição, vínculos e visão 360° |
| `/crm/oportunidades` | Oportunidades | Atual | Lista, Kanban, criação, mudança de etapa/status, próxima ação |
| `/crm/pessoas/:id` | Pessoa 360° | Atual | Cadastro, empresas vinculadas, oportunidades, atividades e tarefas |
| `/crm/empresas/:id` | Empresa 360° | Atual | Cadastro, pessoas vinculadas, oportunidades, atividades e tarefas |
| `/contratos` | Contratos | Atual | Lista canônica com filtros, sem duplicação por unidade |
| `/contratos/:id` | Visão contratual | Atual | Identidade, versão atual, futuras, históricas, serviços, emissor, contatos e eventos |
| `/financeiro` | Financeiro | Atual até Etapa 5 | Resumo por competência, runs, items, estados, valores e exceções |
| `/financeiro/runs/:id` | Billing run | Atual | Resultado de cada contrato considerado, métricas e correlação |
| `/financeiro/items/:id` | Obrigação | Atual | Snapshot imutável, hash, bloqueio e histórico de auditoria/outbox |
| `/tarefas` | Tarefas | **Lacuna parcial** | Não há `GET` geral de tarefas; usar apenas tarefas/next actions já presentes no Kanban e nas visões 360° |
| `/automacoes` | Automações | **Futuro/preparatório** | Criar somente shell/empty state `future/mock`; não há API de fluxos, integrações, execuções ou saúde |

### 4.1 Início

A Home deve priorizar exceção e decisão:

- data atual e saudação;
- **Precisa da sua atenção**;
- próximos 7 dias;
- resumo executivo;
- prioridades/tarefas críticas.

Não criar a seção permanente “Sistema trabalhando”. Falhas relevantes de integrações/automações, quando houver API oficial futura, entram em **Precisa da sua atenção**.

Fontes disponíveis hoje:

- oportunidades e próximas ações: `GET /api/v1/crm/opportunities` ou Kanban por pipeline;
- resumo financeiro por competência: `GET /api/v1/billing/summary`;
- bloqueios financeiros: `GET /api/v1/billing/exceptions`, mediante `billing:review`;
- contratos filtrados: `GET /api/v1/contracts`;
- auditoria recente: `GET /api/v1/control/audit`, mediante `audit:read`.

Limites: não há endpoint de dashboard executivo, listagem global de tarefas, exceções operacionais gerais, contratos a vencer, atividades recentes globais ou saúde de automações. A Home não deve multiplicar consultas 360° para fabricar essas visões. Gráficos financeiros detalhados pertencem ao Financeiro.

### 4.2 CRM

Mapear lista, busca, pessoas, empresas, relacionamento pessoa–empresa, oportunidades, pipelines, Kanban, atividades, tarefas/next actions e Cliente 360°. Pessoa e Empresa são cadastros canônicos do Grupo e podem se vincular a várias unidades. Oportunidade, pipeline, atividade e tarefa possuem `business_unit_id` explícito.

O status da oportunidade (`open`, `won`, `lost`) é diferente da etapa do pipeline. Arrastar no Kanban chama o endpoint de mudança de etapa; marcar perda exige `loss_reason_id`. A próxima ação exibida na oportunidade é a tarefa aberta mais próxima, não um campo duplicado.

### 4.3 Contratos

Existe uma única base canônica de contratos. Nunca duplicar contrato para MR, STK Lab ou Stelli. O filtro/contexto usa `business_unit_id`.

A visão contratual deve separar:

- identidade administrativa;
- estado operacional atual;
- versão corrente;
- versões agendadas/futuras;
- versões históricas;
- serviços ativos/inativos de cada snapshot;
- estabelecimento emissor vindo da versão;
- contatos financeiros versionados;
- eventos de suspensão, retomada, encerramento e renovação;
- hash da configuração quando relevante para auditoria.

O frontend não calcula a versão válida: para uma data arbitrária, usa `GET /contracts/{id}/configuration?date=...`.

### 4.4 Financeiro

Implementado após a Etapa 5:

- competências `YYYY-MM`;
- billing runs e resultado por contrato (`created`, `reused`, `not_eligible`);
- billing items únicos por contrato/competência;
- previstos, prontos e bloqueados;
- valores brutos, cliente, contrato, unidade e emissor;
- códigos/motivos de bloqueio;
- snapshot canônico imutável e SHA-256;
- histórico de auditoria/outbox;
- resumo por competência e unidade;
- reprocessamento seguro que apenas recupera a operação congelada.

**Futuro e ainda não implementado:** NFS-e, documento fiscal, estado fiscal, cálculo tributário, retenções, payload fiscal, certificado, emissão, cancelamento fiscal, substituição, PDF/XML e reconciliação com SEFIN. `ready` não autoriza o frontend a simular qualquer um desses resultados.

### 4.5 Tarefas

Há criação e conclusão de tarefas e leitura de tarefas dentro de Pessoa 360°, Empresa 360° e `next_action` de oportunidades/Kanban. Não há endpoint de listagem geral, leitura individual ou edição de tarefa. Portanto, uma página completa `/tarefas` depende de extensão futura do backend. Até lá, disponibilizar tarefas nos contextos existentes e usar empty/limited state honesto.

### 4.6 Automações

Rota preparatória futura, com a taxonomia visual possível: Fluxos, Integrações, Execuções e Saúde. Não implementar engine genérica de workflow. A inbox, a outbox e logs técnicos não equivalem a um catálogo/estado de automações para usuário final. Atualmente não há endpoints frontend para listar esses quatro grupos.

## 5. Contexto Grupo STK

Hierarquia real:

```text
organization_id (Grupo STK)
└── legal_entity_id
    └── fiscal_establishment_id
        └── business_unit_id (MR | STK Lab | Stelli)
```

- `organization_id` vem do ator autenticado/JWT e é imposto pelo backend; o browser não escolhe outra organização.
- `GET /api/v1/organization` devolve a hierarquia visível para o ator.
- `business_unit_id` é o filtro/escopo de UX para uma unidade.
- `fiscal_establishment_id` identifica estabelecimento fiscal; não é sinônimo de unidade.
- `issuer_establishment_id` é escolhido e validado no contrato pelo backend; o seletor deve usar `GET /contracts/reference-data` e nunca inferir o emissor da unidade.
- Pessoas e empresas podem ter vários `business_unit_ids`; oportunidades, tarefas, atividades, contratos, runs e items têm uma unidade explícita.

Comportamento do `UnitSwitcher`:

- **Grupo STK:** visão consolidada; omitir `business_unit_id` apenas nos endpoints em que o parâmetro é opcional e combinar pipelines/unidades quando necessário;
- **MR/STK Lab/Stelli:** enviar o `business_unit_id` nos endpoints que aceitam o filtro e escolher pipelines da unidade;
- manter contexto no estado global e, idealmente, na URL; trocar contexto invalida queries dependentes;
- jamais criar bancos, tabelas ou cadastros paralelos por unidade.

Limitações atuais:

- `GET /crm/search` pesquisa a organização inteira e não aceita `business_unit_id`; filtrar os resultados pelos `business_unit_ids` no contexto visual, sem tratar isso como autorização;
- endpoints 360° são organizacionais e não recebem filtro de unidade;
- algumas listas CRM aceitam `business_unit_id`, mas `reference-data` traz todas as referências visíveis;
- na implementação atual, `crm:read`/`crm:write` autorizam no nível da organização; o filtro de unidade no CRM organiza a experiência e a coerência de domínio, mas ainda não é uma fronteira de autorização por unidade;
- Contratos e Faturamento aplicam escopo de unidade associado ao papel; fora do escopo, detalhes retornam 404 para não revelar existência;
- não existe endpoint de preferência persistida do contexto selecionado.

## 6. Ctrl+K — comando universal

Criar um único componente global fixo e disponível em todas as telas, acionado por `Ctrl+K` (e `Cmd+K` em macOS), por exemplo:

```text
Buscar, perguntar ou comandar o STK OS...    Ctrl + K    🎙
```

Não mostrar permanentemente quatro abas/botões “Buscar”, “Executar”, “Perguntar” e “Falar”. A intenção será inferida no futuro. Nesta entrega não implementar agente, IA, voz ou execução autônoma.

### Capacidade atual permitida

- pesquisar pessoa, empresa e oportunidade com `GET /api/v1/crm/search?q=...` (mínimo 2, máximo 100 caracteres);
- navegar para rotas e entidades já carregadas;
- abrir Pessoa/Empresa 360° após selecionar um resultado;
- oferecer atalhos puramente locais de navegação.

Busca de contrato, faturamento, tarefa e auditoria não é global hoje. Não simular um índice global no cliente baixando toda a base.

### Preparação futura

O componente pode possuir uma camada de registry para ações existentes, mas cada ação deve declarar endpoint real, capability, contexto, payload, risco e política de confirmação. Mutações existentes que futuramente podem ser registradas incluem CRM, versões/eventos de contratos e geração/reprocessamento de competência. O registry não executa ações sem token/capability e nunca contorna o backend.

Estados obrigatórios: fechado, aberto/inicial, digitando, loading, resultados, vazio, erro, sucesso e permissão negada. Ações sensíveis, destrutivas ou irreversíveis exigem diálogo de confirmação com resumo do alvo e efeito. Hoje, encerramento contratual, geração de competência e mudança de status comercial merecem confirmação explícita. Voz, IA e comandos autônomos permanecem `future/mock`.

## 7. Estados de domínio que a UI deve respeitar

### 7.1 Contratos

Não existe um único enum “vigente/futuro/histórico/suspenso/encerrado”. A UI compõe três dimensões devolvidas pela API:

| Dimensão | Estados atuais | Significado visual |
|---|---|---|
| Administrativo (`administrative_status`) | `draft`, `active`, `archived` | Gestão do cadastro; não define vigência operacional |
| Temporal da versão (`temporal_status`) | `historical`, `current`, `scheduled` | Histórica, vigente na data corrente, futura/agendada |
| Operacional derivado | `active`, `suspended`, `terminated` | Ativo/vigente operacionalmente, suspenso ou encerrado |

Regras de apresentação:

- uma versão `current` pode pertencer a contrato operacionalmente `suspended`;
- `scheduled` significa versão futura, não contrato ativo;
- `terminated` deve ser exibido como encerrado, sem apagar versões históricas;
- `renewed` é evento e referencia uma versão de renovação; não é um quarto estado operacional;
- a primeira versão começa em `start_date`; a API deriva `effective_until` pelo início da próxima versão;
- versões e eventos são append-only.

### 7.2 Faturamento

| Estado do item | Disponibilidade | Semântica correta |
|---|---|---|
| `blocked` | Atual | Obrigação criada, mas impedida por dado inválido ou decisão pendente; mostrar código e motivo |
| `ready` | Atual | Obrigação contratual íntegra e apta a uma futura solicitação fiscal; **não é NFS-e emitida** |
| `requested` | Reservado à Etapa 6 | Solicitação fiscal real; o gerador atual não cria este estado |
| `completed` | Reservado à Etapa 6 | Conclusão fiscal real; o gerador atual não cria este estado |
| `cancelled` | Reservado | Cancelamento lógico depende de decisão futura; o gerador atual não cria este estado |

Runs podem estar `processing`, `completed` ou `completed_with_exceptions`. O resultado de um contrato dentro do run é `created`, `reused` ou `not_eligible`. `not_eligible` não é billing item bloqueado: nenhuma obrigação foi criada.

### 7.3 CRM e tarefas

- oportunidade: `open`, `won`, `lost`;
- tarefa: `open`, `completed`;
- pessoa/empresa/atividade e catálogos: tipicamente `active`/`inactive` quando exposto;
- perda exige motivo; reabertura de oportunidade exige tarefa aberta;
- etapa do pipeline nunca substitui o status da oportunidade.

## 8. Componentes reutilizáveis sugeridos

Criar apenas componentes justificados pelas telas:

- `AppShell`, `Sidebar`, `UnitSwitcher`, `CommandBar`/`CtrlK`;
- `PageHeader`, `AttentionCard`, `KPICompact`;
- `DataTable`, `FilterBar`, `StatusBadge`;
- `EmptyState`, `LoadingState`, `ErrorState`, `PermissionDenied`;
- `Timeline`, `ActivityFeed`, `KanbanBoard`;
- `EntityHeader`, `VersionHistory`, `AuditTrail`, `ExceptionCard`;
- `DetailDrawer`/`DetailPanel`, `ConfirmActionDialog`.

Evitar uma biblioteca genérica excessiva. Componentes de domínio devem receber estados da API e não recalcular regras.

## 9. Restrições técnicas de design e UX

- interface responsiva e acessível;
- navegação completa por teclado e foco visível;
- Ctrl+K global sem conflitar com campos de texto;
- loading, erro, vazio, sucesso e permissão negada claramente distintos;
- nenhuma informação crítica representada apenas por cor; badges precisam de texto/ícone;
- confirmação para ações críticas;
- Home enxuta, orientada a exceção e decisão;
- detalhes profundos nos módulos;
- gráficos financeiros detalhados somente no Financeiro;
- tabelas precisam de alternativa responsiva sem esconder status, bloqueio ou ação crítica;
- drawers/dialogs com foco preso, `Esc`, título acessível e retorno de foco;
- valores, datas e estados devem usar rótulos em português, preservando o valor canônico da API internamente.

## 10. Convenções comuns da API

### Autenticação e erros

Todas as rotas `/api/v1`, exceto `/auth/token` e `/auth/service-token`, exigem Bearer token. Health é público.

- `401`: credencial ausente, inválida ou expirada; limpar estado de sessão e voltar ao login, preservando destino seguro;
- `403`: capability insuficiente; exibir `PermissionDenied`; esconder botão é melhoria de UX, não autorização;
- `404`: recurso inexistente ou fora do escopo; não revelar existência;
- `409`: conflito de domínio ou chave idempotente reutilizada com intenção diferente;
- `422`: payload/parâmetro inválido ou regra de validação declarada;
- `503`: readiness com banco indisponível.

O OpenAPI exportado declara principalmente respostas de sucesso e 422; 401/403/404/409 acima são comportamentos reais dos routers e devem ser tratados.

### Paginação e limites

Não existe paginação geral implementada. As respostas são arrays sem `total`, cursor ou metadados. Há limites fixos não configuráveis pelo cliente: pessoas 100, empresas 100, oportunidades 200, contratos 500 e busca global até 20 resultados por tipo. Auditoria aceita `limit` (padrão 50, mínimo efetivo 1, máximo efetivo 100). As demais listas não declaram paginação. O Lovable não deve inventar `page`, `offset`, `cursor` ou totalizações de servidor e deve tratar uma lista no limite como potencialmente incompleta.

### Idempotência

Toda rota marcada `Sim` abaixo exige header `Idempotency-Key` entre 8 e 255 caracteres. A repetição da mesma chave e intenção devolve o resultado lógico anterior; a mesma chave com payload/intenção diferente retorna 409. GETs e autenticação não usam a chave. `POST /control/inbox` deduplica pelo par `source + external_event_id`, não por header.

### Schemas abreviados usados nas tabelas

Campos com `?` são opcionais/nullable. Listas são `[]`. Datas civis usam `YYYY-MM-DD`; instantes usam ISO 8601.

- `TokenResponse`: `access_token`, `token_type="bearer"`, `expires_in` (segundos).
- `PersonCreate`: `full_name`, `business_unit_ids[]`; opcionais `tax_id`, cidade/UF, notas, origem e contatos.
- `CompanyCreate`: `legal_name`, `business_unit_ids[]`; opcionais nome fantasia, CNPJ, endereço, cidade/UF, site, notas, origem e contatos.
- `PersonSummary`/`CompanySummary`: identidade, status, unidades, contatos e timestamps.
- `OpportunityCreate`: unidade, pipeline, etapa, título, origem e próxima ação; opcionais participantes, produtos, valor/moeda, fechamento e notas.
- `OpportunityResponse`: identidade comercial, status, unidade/pipeline/etapa, participantes, produtos, valor, cliente, última interação, entrada na etapa e `next_action`.
- `ActivityCreate`: unidade, tipo, instante, resumo, origem e executor; vínculos opcionais a oportunidade/pessoa/empresa.
- `TaskCreate`: unidade, título e vencimento; prioridade e vínculos opcionais.
- `ContractCreate`: unidade, empresa cliente, número interno, início e tipo; assinatura, responsável e notas opcionais.
- `ContractVersionCreate`: vigência, emissor, frequência/modelo/valor, tipo e motivo da alteração, `services[]` e `financial_contacts[]`; inclui condições opcionais de cobrança/reajuste.
- `ContractDetail`: resumo + notas controladas + todas as versões e eventos operacionais.
- `BillingGenerate`: `business_unit_id`, `competence_month` (`YYYY-MM`), `run_type` (`manual|scheduled`, padrão `manual`) e `causation_id?`.
- `BillingRunResponse`: identificação/contexto, competência, tipo/status, timezone, versão da regra, correlação, métricas e resultados por contrato.
- `BillingItemDetail`: resumo do item + `snapshot` e `history[]` de auditoria/outbox.

## 11. APIs atuais consolidadas

As 49 operações abaixo existem no OpenAPI atual. `Bearer` é implícito em toda capability diferente de “Pública”. Em “Erros”, somam-se 401/403 nas rotas protegidas e 422 quando há entrada validada.

### 11.1 Health e Auth

| Método e endpoint | Finalidade / entidade | Capability | Parâmetros e filtros | Entrada → resposta | Paginação | Erros relevantes | Idempotency-Key |
|---|---|---|---|---|---|---|---|
| `GET /health/live` | Liveness da API | Pública | — | — → `{status, version}` | Não | — | Não |
| `GET /health/ready` | Readiness API/banco | Pública | — | — → `{status, database}` | Não | 503 | Não |
| `POST /api/v1/auth/token` | Login de usuário | Pública | — | `{email, password}` → `TokenResponse` | Não | 401, 422 | Não |
| `POST /api/v1/auth/service-token` | Token de integração server-to-server; **não usar no browser** | Pública | — | `{client_id, client_secret}` → `TokenResponse` | Não | 401, 422 | Não |

### 11.2 Organização e contexto

| Método e endpoint | Finalidade / entidade | Capability | Parâmetros e filtros | Entrada → resposta | Paginação | Erros relevantes | Idempotency-Key |
|---|---|---|---|---|---|---|---|
| `GET /api/v1/organization` | Hierarquia Grupo → entidades → estabelecimentos → unidades | `organization:read` | — | — → `OrganizationResponse` aninhada | Não | 404 | Não |
| `PATCH /api/v1/organization/business-units/{unit_id}` | Renomear unidade | `organization:write` | `unit_id` path | `{name}` → `BusinessUnitResponse` | Não | 404, 409, 422 | Sim |

### 11.3 CRM

| Método e endpoint | Finalidade / entidade | Capability | Parâmetros e filtros | Entrada → resposta | Paginação | Erros relevantes | Idempotency-Key |
|---|---|---|---|---|---|---|---|
| `GET /api/v1/crm/reference-data` | Catálogos, unidades, origens, produtos, perdas, pipelines/etapas | `crm:read` | — | — → `ReferenceDataResponse` | Não | — | Não |
| `GET /api/v1/crm/people` | Listar/buscar pessoas | `crm:read` | `business_unit_id?`, `q?` | — → `PersonSummary[]` | Sem página; hard cap 100 | 422 | Não |
| `POST /api/v1/crm/people` | Criar pessoa canônica | `crm:write` | — | `PersonCreate` → `PersonSummary` (201) | Não | 409 CPF, 422 | Sim |
| `PATCH /api/v1/crm/people/{person_id}` | Atualizar campos permitidos | `crm:write` | `person_id` | `PersonUpdate` (nome/cidade/UF/notas/status) → `PersonSummary` | Não | 404, 409, 422 | Sim |
| `GET /api/v1/crm/companies` | Listar/buscar empresas | `crm:read` | `business_unit_id?`, `q?` | — → `CompanySummary[]` | Sem página; hard cap 100 | 422 | Não |
| `POST /api/v1/crm/companies` | Criar empresa canônica | `crm:write` | — | `CompanyCreate` → `CompanySummary` (201) | Não | 409 CNPJ, 422 | Sim |
| `PATCH /api/v1/crm/companies/{company_id}` | Atualizar campos permitidos | `crm:write` | `company_id` | `CompanyUpdate` → `CompanySummary` | Não | 404, 409, 422 | Sim |
| `POST /api/v1/crm/relationships/person-company` | Vincular pessoa e empresa | `crm:write` | — | `{person_id, company_id, role, is_primary?}` → vínculo | Não | 404, 409, 422 | Sim |
| `GET /api/v1/crm/opportunities` | Listar oportunidades | `crm:read` | `business_unit_id?`, `pipeline_id?`, `status?` | — → `OpportunityResponse[]` | Sem página; hard cap 200 | 422; status inválido | Não |
| `POST /api/v1/crm/opportunities` | Criar oportunidade e próxima ação | `crm:write` | — | `OpportunityCreate` → `OpportunityResponse` (201) | Não | 404, 422 | Sim |
| `GET /api/v1/crm/kanban/{pipeline_id}` | Obter colunas e cards do Kanban | `crm:read` | `pipeline_id` | — → `KanbanResponse` | Não | 404 | Não |
| `PATCH /api/v1/crm/opportunities/{opportunity_id}/stage` | Mover etapa com histórico | `crm:write` | `opportunity_id` | `{stage_id, note?, source?}` → `OpportunityResponse` | Não | 404, 409 fechado, 422 | Sim |
| `PATCH /api/v1/crm/opportunities/{opportunity_id}/status` | Ganhar, perder ou reabrir | `crm:write` | `opportunity_id` | `{status: open\|won\|lost, loss_reason_id?, note?}` → `OpportunityResponse` | Não | 404, 409, 422 | Sim |
| `POST /api/v1/crm/activities` | Registrar interação | `crm:write` | — | `ActivityCreate` → `ActivityResponse` (201) | Não | 404, 422 | Sim |
| `GET /api/v1/crm/search` | Busca global CRM | `crm:read` | `q` obrigatório, 2–100 caracteres | — → `SearchResult[]` (`person\|company\|opportunity`) | Sem página; até 20 por tipo | 422 | Não |
| `GET /api/v1/crm/people/{person_id}/360` | Pessoa 360° | `crm:read` | `person_id` | — → pessoa, empresas, oportunidades, atividades, tarefas | Não | 404 | Não |
| `GET /api/v1/crm/companies/{company_id}/360` | Empresa 360° | `crm:read` | `company_id` | — → empresa, pessoas, oportunidades, atividades, tarefas | Não | 404 | Não |
| `POST /api/v1/crm/imports` | Importação controlada de até 100 linhas | `crm:import` | — | `{source_label, rows[]}` → contagens e resultados por linha (201) | Não | 409, 422 | Sim |

### 11.4 Contratos

| Método e endpoint | Finalidade / entidade | Capability | Parâmetros e filtros | Entrada → resposta | Paginação | Erros relevantes | Idempotency-Key |
|---|---|---|---|---|---|---|---|
| `GET /api/v1/contracts/reference-data` | Opções válidas de unidade, cliente, emissor, serviço e contato | `contracts:read` | — | — → `ContractReferenceData` | Não | — | Não |
| `GET /api/v1/contracts` | Lista canônica de contratos | `contracts:read` | `business_unit_id?`, `customer_company_id?`, `administrative_status?`, `issuer_establishment_id?`, `valid_on?` | — → `ContractSummary[]` | Sem página; hard cap 500 | 404 fora do escopo, 422 | Não |
| `POST /api/v1/contracts` | Criar identidade administrativa | `contracts:create` | — | `ContractCreate` → `ContractSummary` (201) | Não | 409 número interno, 422 | Sim |
| `GET /api/v1/contracts/{contract_id}` | Detalhe completo | `contracts:read` | `contract_id` | — → `ContractDetail` | Não | 404 | Não |
| `GET /api/v1/contracts/{contract_id}/history` | Histórico completo; hoje mesma forma de `ContractDetail` | `contracts:read` | `contract_id` | — → `ContractDetail` | Não | 404 | Não |
| `GET /api/v1/contracts/{contract_id}/configuration` | Configuração válida em data | `contracts:read` | `contract_id`; query `date` obrigatória | — → `ContractConfiguration` | Não | 404 sem configuração, 422 | Não |
| `POST /api/v1/contracts/{contract_id}/versions` | Publicar próxima versão não retroativa | `contracts:version` | `contract_id` | `ContractVersionCreate` → versão (201) | Não | 404, 409 sobreposição, 422 | Sim |
| `POST /api/v1/contracts/{contract_id}/schedule` | Agendar versão futura | `contracts:version` | `contract_id` | `ContractVersionCreate` com `effective_from` futuro → versão (201) | Não | 404, 409, 422 | Sim |
| `POST /api/v1/contracts/{contract_id}/suspend` | Suspender por evento | `contracts:suspend` | `contract_id` | `{effective_on, reason, source?}` → evento (201) | Não | 404, 409 estado/ordem, 422 | Sim |
| `POST /api/v1/contracts/{contract_id}/resume` | Retomar por evento | `contracts:resume` | `contract_id` | `OperationalEventCreate` → evento (201) | Não | 404, 409 estado/ordem, 422 | Sim |
| `POST /api/v1/contracts/{contract_id}/terminate` | Encerrar por evento | `contracts:terminate` | `contract_id` | `OperationalEventCreate` → evento (201) | Não | 404, 409 estado/versão futura, 422 | Sim |
| `POST /api/v1/contracts/{contract_id}/renew` | Renovar criando versão e evento ligados | `contracts:version` | `contract_id` | `ContractVersionCreate` com `change_type=renewal` → `ContractDetail` (201) | Não | 404, 409, 422 | Sim |

### 11.5 Faturamento

| Método e endpoint | Finalidade / entidade | Capability | Parâmetros e filtros | Entrada → resposta | Paginação | Erros relevantes | Idempotency-Key |
|---|---|---|---|---|---|---|---|
| `POST /api/v1/billing/runs` | Gerar competência determinística | `billing:generate` | — | `BillingGenerate` → `BillingRunResponse` (201) | Não | 404 escopo, 409 idempotência, 422 unidade/competência | Sim |
| `GET /api/v1/billing/runs` | Listar runs | `billing:read` | `competence_month?`, `business_unit_id?` | — → `BillingRunResponse[]` | Não | 404 escopo, 422 | Não |
| `GET /api/v1/billing/runs/{run_id}` | Detalhar run e contratos considerados | `billing:read` | `run_id` | — → `BillingRunResponse` | Não | 404 | Não |
| `POST /api/v1/billing/runs/{run_id}/reprocess` | Recuperar/reprocessar somente operação segura congelada | `billing:reprocess` | `run_id` | corpo vazio → `BillingRunResponse` | Não | 404, 409 | Sim |
| `GET /api/v1/billing/items` | Listar obrigações | `billing:read` | `competence_month?`, `business_unit_id?`, `customer_company_id?`, `status?`, `run_id?` | — → `BillingItemSummary[]` | Não | 404 escopo, 422 | Não |
| `GET /api/v1/billing/items/{item_id}` | Detalhar obrigação, snapshot e história | `billing:read` | `item_id` | — → `BillingItemDetail` | Não | 404 | Não |
| `GET /api/v1/billing/exceptions` | Listar itens bloqueados/exceções | `billing:review` | `competence_month?`, `business_unit_id?` | — → `BillingExceptionResponse[]` | Não | 404 escopo, 422 | Não |
| `GET /api/v1/billing/summary` | Resumo financeiro da competência | `billing:read` | `competence_month` obrigatório; `business_unit_id?` | — → valores/contagens e `by_business_unit[]` | Não | 404 escopo, 422 | Não |

### 11.6 Tarefas

| Método e endpoint | Finalidade / entidade | Capability | Parâmetros e filtros | Entrada → resposta | Paginação | Erros relevantes | Idempotency-Key |
|---|---|---|---|---|---|---|---|
| `POST /api/v1/crm/tasks` | Criar tarefa/próxima ação vinculável | `crm:write` | — | `TaskCreate` → `TaskResponse` (201) | Não | 404, 422 | Sim |
| `PATCH /api/v1/crm/tasks/{task_id}/complete` | Concluir tarefa | `crm:write` | `task_id`; corpo vazio | — → `TaskResponse` | Não | 404, 409, 422 | Sim |

### 11.7 Controle e auditoria

| Método e endpoint | Finalidade / entidade | Capability | Parâmetros e filtros | Entrada → resposta | Paginação | Erros relevantes | Idempotency-Key |
|---|---|---|---|---|---|---|---|
| `GET /api/v1/control/audit` | Trilha oficial recente consumível pela UI administrativa | `audit:read` | `limit?` padrão 50, clamp 1–100 | — → `AuditEventResponse[]` | Apenas `limit`; sem cursor | 422 | Não |
| `POST /api/v1/control/inbox` | Ingerir evento externo deduplicado; uso de integração, não UI comum | `events:ingest` | — | `{source, external_event_id, event_type, payload}` → status/duplicidade/correlação (201) | Não | 409 payload divergente, 422 | Não; deduplicação própria |
| `POST /api/v1/control/exceptions` | Registrar exceção operacional; normalmente integração/backend | `exceptions:write` | — | `{exception_type, severity, title, context?}` → `ExceptionResponse` (201) | Não | 422 | Não |

Não há endpoint atual para listar exceções operacionais gerais, outbox ou inbox. O frontend não deve consultar logs técnicos ou banco para preencher essa lacuna.

## 12. Segurança frontend

### Estratégia atual

- usuário envia e-mail/senha para `/auth/token`;
- backend valida hash Argon2 e devolve JWT Bearer HS256 com `sub`, `kind`, permissões, issuer, emissão, expiração, JTI;
- duração padrão atual: 15 minutos, configurável no backend entre 1 e 60;
- a cada request, o backend cruza permissões do token com as permissões atuais persistidas;
- ator precisa estar ativo e pertencer à organização;
- service accounts têm endpoint separado e não devem existir no browser.

### Requisitos para o Lovable

- preferir sessão em memória no baseline atual; não persistir senha;
- não persistir service token; não colocar credenciais em localStorage, código, bundle ou URL;
- não há refresh endpoint: ao expirar, voltar ao login;
- 401 encerra a sessão local; 403 mantém a sessão e mostra falta de permissão;
- gates de UI podem usar um conjunto de capabilities obtido por uma futura API de sessão; **hoje não existe `/me` nem capabilities na resposta de login**, então não inventar autorização client-side;
- o backend sempre verifica capability e, quando aplicável, unidade;
- nenhuma autorização pode depender apenas de ocultar botão/rota;
- operações sensíveis sempre passam pelo backend e usam confirmação + idempotência;
- nunca expor `STK_JWT_SECRET`, senha de banco, client secret, certificado ou segredo de integrações;
- para deploy Lovable em outra origem, a allowlist CORS do backend precisará de alteração operacional autorizada; não liberar `*` com credenciais.

Lacunas de identidade ainda abertas: provedor de produção, MFA, refresh/revogação distribuída, recuperação de senha e endpoint de perfil/sessão. Não escolher Supabase Auth ou outro provedor dentro do frontend sem autorização arquitetural.

## 13. Dados mockados e funcionalidades futuras

Mocks são permitidos somente se:

- estiverem isolados em adapters/fixtures removíveis;
- cada tela/bloco exibir claramente `future/mock` em ambiente de demonstração;
- nunca forem combinados com totais ou estados produtivos;
- nunca simularem sucesso de uma operação real inexistente;
- estiverem desabilitados por padrão em build conectado à API real.

Obrigatoriamente futuros/mocados: NFS-e, documento/estado fiscal, Outlook, n8n, APIs bancárias, boleto/pagamento, voz, IA, comandos autônomos e saúde/execuções de automações.

## 14. Lacunas que impedem telas completas hoje

| Necessidade visual | Lacuna atual | Conduta do frontend |
|---|---|---|
| Home executiva completa | Sem endpoint agregado | Usar apenas consultas existentes; não fabricar métricas |
| “Precisa da sua atenção” geral | Sem GET de exceções operacionais; só bloqueios de billing | Mostrar billing quando autorizado e estados honestos para demais fontes |
| Próximos 7 dias/tarefas gerais | Sem GET global de tarefas | Usar `next_action` de oportunidades e tarefas dos 360°, sem N+1 massivo |
| Busca universal completa | Busca atual cobre apenas pessoa, empresa e oportunidade | Limitar resultados atuais; indicar categorias futuras |
| Página completa de tarefas | Sem listar/editar/reabrir tarefa | Manter ações nos contextos existentes |
| Automações | Sem APIs de fluxos, integrações, runs ou saúde | Somente shell `future/mock` |
| Sessão/capabilities no cliente | Sem `/me`, refresh e capabilities no login | Não inferir autorização; tratar respostas do backend |
| Paginação de grandes listas | Ausente | Não inventar parâmetros; planejar evolução de API antes de escala |
| Dashboard/relatórios | Sem endpoints dedicados | Evitar agregações caras ou inconsistentes no browser |
| Fiscal | Etapa 6 não iniciada | Não mostrar emissão/cancelamento/reconciliação como funcional |

## 15. Critérios de aceite do frontend produzido no Lovable

- usa apenas endpoints listados como atuais neste documento/OpenAPI;
- possui uma única configuração de base URL da STK OS API;
- não contém Supabase/schema/backend paralelo;
- sidebar segue Início, CRM, Contratos, Financeiro, Tarefas, Automações;
- Grupo/MR/STK Lab/Stelli aparecem como contexto, não módulos;
- Ctrl+K é global e único, sem IA/voz/comando falsos;
- estados contratuais e financeiros não são fundidos ou reinterpretados;
- `ready` nunca é rotulado como nota emitida;
- todas as mutações exigidas enviam idempotency key;
- 401, 403, 404, 409 e 422 têm UX distinta;
- loading/error/empty/permission denied são acessíveis;
- mocks estão isolados e marcados `future/mock`;
- nenhuma credencial ou regra financeira está no bundle;
- não há acesso direto ao PostgreSQL.

# PROMPT TÉCNICO PARA LOVABLE

Você irá desenvolver o frontend premium do **STK OS V1**, plataforma operacional central do Grupo STK. Este prompt técnico será fornecido junto com um documento separado de direção visual. Siga a direção visual separada sem alterar as fronteiras técnicas abaixo.

## Missão

Crie a camada visual e de interação em Next.js/React/TypeScript consumindo a **STK OS API existente**. O backend já existe em FastAPI com PostgreSQL e é a única fonte oficial de dados, regras, estados, autorização, idempotência e auditoria.

Arquitetura obrigatória:

```text
Frontend Lovable → STK OS API → FastAPI/PostgreSQL
```

Não recrie o backend. Não crie Supabase, banco, schema, migrations, edge functions, autenticação alternativa, APIs próprias ou regras financeiras sem autorização explícita. O browser nunca acessa PostgreSQL diretamente.

## Stack e integração

- mantenha Next.js, React e TypeScript;
- use uma única base URL pública da API (`NEXT_PUBLIC_STK_API_URL` pode conter somente a URL);
- use JSON/HTTPS e JWT Bearer de usuário;
- nunca use `/auth/service-token` no browser;
- mutações indicadas no handoff exigem `Idempotency-Key` de 8–255 caracteres;
- trate `X-Correlation-ID`, 401, 403, 404, 409 e 422;
- trate valores decimais como strings para preservar precisão;
- não há refresh token, `/me` ou paginação geral atualmente;
- a origem de produção precisará estar autorizada no CORS do backend.

## Navegação

Implemente a sidebar principal nesta ordem:

1. Início
2. CRM
3. Contratos
4. Financeiro
5. Tarefas
6. Automações

Não crie MR, STK Lab e Stelli como módulos. Crie um seletor de contexto com Grupo STK, MR, STK Lab e Stelli. Grupo STK consolida; uma unidade aplica `business_unit_id` onde a API aceita esse filtro. Pessoas e empresas são canônicas e multiunidade. Contratos também são uma base única.

## Módulos atuais

- CRM: referências, pessoas, empresas, vínculos, oportunidades, Kanban, etapas/status, atividades, tarefas vinculadas, busca e Pessoa/Empresa 360°;
- Contratos: referências, lista/filtros, identidade administrativa, versão corrente, versões históricas e futuras, serviços, emissor, contatos, consulta por data e eventos operacionais;
- Financeiro até Etapa 5: competências, billing runs, billing items, resumos, valores brutos, prontos, bloqueados, exceções, snapshots imutáveis e histórico;
- Auditoria: leitura recente via `/api/v1/control/audit` quando autorizada.

Use exclusivamente as APIs atuais descritas na seção “APIs atuais consolidadas” deste handoff e confira `contracts/api/openapi.json`. Não invente endpoint.

## Home

Prepare `/` com data, saudação, “Precisa da sua atenção”, próximos 7 dias, resumo executivo e prioridades críticas. Não crie “Sistema trabalhando”. Use somente dados realmente disponíveis. Como não existe endpoint agregado de Home nem listagem global de tarefas/exceções, mostre limited/empty states honestos em vez de números inventados. Falhas futuras de integração entram em “Precisa da sua atenção”. Gráficos financeiros detalhados ficam em Financeiro.

## Ctrl+K

Crie um único comando universal global, disponível em todas as telas, com atalho Ctrl+K/Cmd+K e texto semelhante a “Buscar, perguntar ou comandar o STK OS...”. Não mostre quatro modos permanentes. Hoje ele pode pesquisar pessoa, empresa e oportunidade por `/api/v1/crm/search` e navegar localmente. Não implemente IA, agente, voz ou execução autônoma. Prepare estados loading, vazio, erro, sucesso e permissão negada. Ações futuras sensíveis precisam de capability e confirmação.

## Estados obrigatórios

Contratos têm três dimensões separadas:

- administrativo: `draft|active|archived`;
- versão temporal: `historical|current|scheduled`;
- operacional: `active|suspended|terminated`.

Não as funda em um enum artificial.

Billing items: `blocked|ready|requested|completed|cancelled`. A Etapa 5 cria apenas `blocked` ou `ready`. **`ready` não significa NFS-e emitida.** Runs: `processing|completed|completed_with_exceptions`. Resultado por contrato: `created|reused|not_eligible`.

Oportunidades: `open|won|lost`. Tarefas: `open|completed`. Status comercial não é etapa de pipeline.

## Segurança e UX

- não armazene senha, service account ou segredo no frontend;
- não use `NEXT_PUBLIC_*` para secrets;
- ocultar botão não substitui autorização do backend;
- 401 encerra sessão local; 403 mostra permissão negada;
- confirme encerramento contratual, geração de competência e outras ações críticas;
- preserve acessibilidade, teclado, foco, responsividade e estados loading/error/empty;
- nunca use apenas cor para informação crítica;
- não recalcule elegibilidade, versão válida, emissor, valores ou snapshots no browser.

## Futuro / não implementar como real

NFS-e, documento/estado fiscal, emissão, cancelamento, substituição, reconciliação SEFIN, tributos, certificados, Outlook, n8n, APIs bancárias, voz, IA, MCP, comandos autônomos e engine de automação ainda não existem. Se a demonstração visual exigir representação, isole e marque explicitamente como `future/mock`, sem misturar com dados produtivos e sem simular sucesso operacional.

## Entrega esperada

Entregue o frontend e seus componentes de apresentação conectáveis à STK OS API, mantendo adapters tipados e mocks futuros removíveis. Não altere backend, banco ou OpenAPI. Se uma tela depender de API ausente, registre a dependência e apresente estado indisponível honesto; não crie backend paralelo.

---

**FRONTEND HANDOFF APROVADO — PRONTO PARA CURADORIA VISUAL E LOVABLE**
