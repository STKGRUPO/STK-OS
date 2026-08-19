# Relatório de Revisão Técnica — STK OS V1

**Data da revisão:** 18 de agosto de 2026  
**Documento revisado:** `PRD-STK-OS-V1.md`  
**Natureza:** revisão de arquitetura e prontidão; nenhuma implementação foi iniciada.

## 1. Veredito executivo

O STK OS é tecnicamente viável e o PRD tem bons fundamentos: fonte oficial de estado, separação entre IA e regras determinísticas, auditoria, controle por competência e evolução gradual da autonomia. A direção do produto deve ser mantida.

O PRD, porém, **ainda não está pronto para implementação**. Ele define corretamente o “o quê”, mas deixa indefinidos alguns “como” que afetam integridade financeira, segurança e custo de manutenção. O maior risco é transformar o n8n em backend implícito: se elegibilidade, duplicidade, transições e gravações críticas viverem nos workflows, o sistema será difícil de testar, versionar e operar com segurança.

A recomendação é uma V1 modular, mas não distribuída em microserviços:

- frontend web;
- um backend transacional do STK OS;
- PostgreSQL gerenciado como fonte oficial;
- armazenamento privado de documentos;
- n8n como orquestrador de integrações;
- adaptador em torno do sistema Python de NFS-e;
- caixa de eventos persistente, auditoria e fila de exceções;
- IA somente em tarefas probabilísticas e sempre atrás de políticas determinísticas.

O primeiro corte deve provar **CRM manual + contratos + faturamento recorrente MR de ponta a ponta**. Os outros três workflows continuam no roadmap, mas não devem ser condição para a primeira entrada em produção.

**Parecer: NÃO APROVADO PARA IMPLEMENTAÇÃO.**

Aprova-se a direção do produto e autoriza-se apenas a fase de definição técnica, prototipação descartável e inspeção das integrações. As decisões bloqueantes estão nas seções 4 e 18.

---

## 2. Principais riscos encontrados

| Prioridade | Risco | Consequência | Tratamento recomendado |
|---|---|---|---|
| Crítica | n8n assumir regras e gravações centrais | duplicidade, estados impossíveis, difícil teste e dependência excessiva do workflow | backend deve ser dono de comandos, invariantes e transações |
| Crítica | modelo financeiro insuficiente | NF emitida sem rastreabilidade, dificuldade de reemissão, estorno, cobrança e conciliação | separar execução de faturamento, item por competência, solicitação de emissão, nota e entrega |
| Crítica | “unidade” diretamente em Pessoa e Empresa | duplicação de cadastros ou perda da visão consolidada quando um contato atende várias unidades | cadastros globais ao Grupo, relacionados a uma ou mais unidades por tabelas de vínculo |
| Crítica | autonomia descrita apenas como status | um campo `AUTÔNOMO` não controla versão, escopo, ações permitidas nem rollback | política de autonomia por versão, ação, ambiente e faixa de risco |
| Alta | etapas misturando venda e entrega | métricas de conversão distorcidas; especialmente Lab e Stelli | oportunidade termina em ganho/perda; agendamento/execução pertence a entidade operacional futura ou mínima |
| Alta | logs contendo payloads de WhatsApp, e-mail e IA | exposição de dados pessoais e potencialmente sensíveis | minimização, redação, retenção e acesso segregado; log técnico não é prontuário |
| Alta | agentes com paridade genérica ao usuário | ampliação de privilégio e ações irreversíveis indevidas | APIs por capacidade, escopos estreitos, limites e autorização por ação |
| Alta | recebimento de eventos sem inbox/idempotência | webhooks repetidos criam leads, atividades, e-mails ou NFs duplicados | evento persistido com identificador único antes do processamento |
| Alta | dependência prematura de Lovable no backend | regras espalhadas, acesso direto ao banco, dificuldade de revisão e migração | usar para protótipo/frontend; backend e migrações ficam no repositório sob controle do projeto |
| Média | quatro automações em uma única V1 | atraso e baixa qualidade operacional | colocar somente faturamento MR no marco inicial; liberar as demais sequencialmente |
| Média | dashboard amplo antes de semântica dos dados | números inconsistentes com aparência de precisão | definir métricas e eventos primeiro; começar com painel operacional mínimo |
| Média | exclusão permitida sem política | quebra de auditoria e referências | arquivamento/soft delete para registros de negócio; exclusão física só por processo controlado |

---

## 3. Decisões do PRD que eu manteria

1. **STK OS como fonte oficial do estado operacional.** É a decisão arquitetural mais importante.
2. **n8n como orquestrador, não como produto principal.** A intenção está correta; a fronteira precisa apenas ser explicitada.
3. **Regra determinística antes de IA.** Valores, datas, duplicidade, permissões e transições não devem ser delegados a modelos.
4. **Unicidade contrato + competência.** Deve ser garantida pelo banco, não apenas conferida no workflow.
5. **Histórico permanente de etapas e auditoria de ações.** São necessários para métricas e autonomia.
6. **Status separado de etapa.** Deve ser preservado e aplicado de forma consistente; “Ganho” e “Perdido” deixam de ser etapas.
7. **Integração do sistema Python existente.** Reescrita agora criaria risco sem benefício comprovado.
8. **STK Lab fora do domínio clínico.** O limite deve ser reforçado tecnicamente e por política.
9. **API programática para operações importantes.** A API precede agentes e MCP.
10. **Autonomia progressiva e capacidade de suspensão.** O conceito é correto, com controles adicionais.
11. **Migração incremental.** Clientes, contratos e leads ativos primeiro é o corte correto.
12. **Escopo explicitamente fora de ERP, contabilidade e sistema laboratorial.** Deve continuar fora.
13. **Medição de impacto.** ROI é útil, mas o dashboard de capacidade liberada pode esperar até haver dados confiáveis.

---

## 4. Decisões que eu mudaria

### 4.1 Fluxo arquitetural

O fluxo genérico do PRD — evento → n8n → regras/IA → STK OS → ação → logs — é aceitável para ilustração, mas errado como regra universal. Ele coloca o n8n antes da persistência durável e sugere que as regras centrais podem morar nele.

O padrão recomendado é:

**evento externo → validação/autenticação → inbox persistente → orquestração → comando no backend → transação no STK OS → outbox → ação externa → retorno/reconciliação**

Para uso da interface, o caminho é ainda mais simples:

**frontend → backend → banco → resposta**

A interface nunca deve depender de um workflow do n8n para operações comuns do CRM.

### 4.2 Unidade de negócio

Remover `unidade_relacionada` como atributo único de Pessoa e Empresa. Uma pessoa ou empresa pode se relacionar com MR e Stelli simultaneamente sem duplicação cadastral. O vínculo com unidade deve ser muitos-para-muitos, com status, responsável e origem próprios.

Oportunidade, pipeline, contrato e faturamento continuam pertencendo a uma unidade específica.

### 4.3 Pipelines

- “Ganho” e “Perdido” não devem ser etapas de MR ou Stelli B2B; são estados terminais da oportunidade.
- No Lab, “Compareceu”, “Atendimento concluído” e “Pós-atendimento” já são execução de serviço, não venda. Na primeira versão podem permanecer apenas se conscientemente tratados como um pipeline operacional; o modelo de dados não deve presumir que todo pipeline é comercial.
- Em Stelli B2C, pagamento, onboarding, entrega e próxima oferta também misturam venda, pedido e relacionamento. Oportunidade deve encerrar em ganho; o restante migra futuramente para pedido/entrega/customer success.

### 4.4 Próxima ação

Não armazenar “próxima ação” como texto duplicado na oportunidade e também como atividade. Criar uma tarefa aberta, com prazo, responsável e status. A próxima ação do cartão é a tarefa aberta mais próxima; se houver necessidade de desempenho, pode existir um campo derivado/cache controlado pelo backend.

### 4.5 Faturamento

“Faturamento” no PRD concentra competência, NF, e-mail, boleto e pagamento em um único registro. Isso funcionaria apenas no caso feliz. Separar no mínimo:

- execução mensal de faturamento;
- item de contrato/competência;
- solicitação de emissão;
- nota fiscal emitida;
- documento;
- tentativa de envio.

Recebível, boleto e pagamento entram somente quando a integração bancária for priorizada.

### 4.6 Agentes

Substituir o requisito “tudo que o usuário faz poderá ser feito por agente” por:

> Toda ação operacional elegível terá um comando autenticado, auditável e idempotente. Cada agente receberá somente as capacidades necessárias, com limites de valor, unidade, entidade, ambiente e modo de aprovação.

Exclusão, alteração de permissão, acesso a secrets, cancelamento fiscal e exportação massiva não devem ser capacidades genéricas de agentes.

### 4.7 Ambientes e versões

O status de maturidade não pode estar apenas no “workflow”. Ele deve estar em uma **versão implantada** por ambiente. Produção pode ter a versão 3 autônoma enquanto a versão 4 está em teste.

Adicionar modo de **sombra** dentro da validação: o fluxo produz a decisão e a ação proposta, mas não executa o efeito externo. Isso permite comparar humano e automação sem risco.

### 4.8 Lovable

Lovable pode acelerar protótipo e frontend. Não deve ser autoridade sobre schema, autorização, regras financeiras ou deploy de produção. A documentação do produto permite sincronização/exportação para GitHub e implantação externa, mas a saída é de Lovable para GitHub, não um ciclo bidirecional completo; isso exige disciplina de propriedade do código. Consulte [integração Lovable–GitHub](https://docs.lovable.dev/integrations/github) e [implantação fora do Lovable Cloud](https://docs.lovable.dev/tips-tricks/external-deployment-hosting).

---

## 5. Arquitetura técnica recomendada

### 5.1 Forma arquitetural

**Monólito modular com processamento assíncrono**, não microserviços.

Módulos internos:

- identidade e autorização;
- cadastros e CRM;
- contratos e faturamento;
- automações e exceções;
- integrações;
- documentos;
- auditoria e métricas.

Essa forma mantém transações simples e permite separar serviços no futuro somente quando houver volume ou equipe que justifique.

### 5.2 Fonte de verdade e fronteiras

- **PostgreSQL:** estado oficial de negócio.
- **Backend STK OS:** único dono das regras, autorização, transações e comandos.
- **n8n:** coordena chamadas, esperas e conectores; não decide invariantes.
- **Sistema Python:** emissor fiscal atrás de contrato programático estável.
- **Provedores externos:** nunca são considerados atualizados apenas porque a requisição foi enviada; retorno e reconciliação confirmam o resultado.
- **Logs do n8n:** úteis para diagnóstico, mas não são a auditoria oficial. A própria documentação informa que dados de execução são podados por idade/quantidade e recomenda controlar o que é salvo; portanto, a trilha de negócio deve viver no STK OS. Veja [gestão de dados de execução do n8n](https://github.com/n8n-io/n8n-docs/blob/main/docs/deploy/host-n8n/configure-n8n/scaling/manage-execution-data.md).

### 5.3 Eventos confiáveis

Adotar os padrões inbox/outbox:

- **Inbox:** grava um webhook recebido, seu provedor e identificador único antes de processá-lo.
- **Outbox:** a mesma transação que muda o estado de negócio registra o evento que deve ser publicado.
- Um worker entrega eventos pendentes ao n8n e marca tentativas.
- Consumidores aceitam repetição e usam chave de idempotência.

Isso evita a situação “o banco gravou, mas o n8n não recebeu” ou “o n8n repetiu e emitiu duas vezes”.

### 5.4 Síncrono versus assíncrono

| Operação | Modo |
|---|---|
| login, leitura, busca, CRUD de CRM | síncrono via backend |
| mover etapa e criar histórico | uma transação síncrona |
| criar execução mensal e itens de competência | comando síncrono curto; processamento posterior assíncrono |
| emitir NFS-e | assíncrono |
| enviar e-mail/WhatsApp | assíncrono |
| classificar mensagem com IA | assíncrono, salvo quando a experiência exigir resposta imediata |
| receber webhook | confirmar rapidamente após persistência; processar assíncrono |
| importação em massa | assíncrono, com relatório de erros |
| dashboards | consulta síncrona a visões; atualização agregada posterior se necessário |

### 5.5 Diagrama textual

> **Usuário** → Frontend → Backend STK OS → PostgreSQL / Storage  
> **Canais externos** → Adaptadores de entrada → Inbox no STK OS  
> **Scheduler / Inbox / Outbox** → n8n → APIs do Backend  
> **Backend** → Regras e políticas → transação → Outbox  
> **n8n** → Outlook / WhatsApp / adaptador Python / OpenAI  
> **Sistemas externos** → callbacks ou consulta de status → Inbox  
> **Tudo que altera negócio** → auditoria + execução + métricas + exceção  
> **Falhas permanentes** → fila de exceções → painel operacional → reprocessamento controlado

### 5.6 Escalabilidade

Não é necessário Redis ou arquitetura distribuída no início. Um worker e uma fila baseada em registros de outbox são suficientes para o volume esperado, desde que medido. Se concorrência e tempo de fila crescerem, o n8n oferece modo fila com workers e Redis; a própria documentação o apresenta como o modo de melhor escalabilidade. Ver [configuração oficial de queue mode](https://github.com/n8n-io/n8n-docs/blob/main/docs/deploy/host-n8n/configure-n8n/basic-configuration/use-environment-variables/queue-mode.md).

---

## 6. Modelo de dados recomendado para a V1

### 6.1 Princípios

- identificadores internos imutáveis;
- `organization_id` em todos os dados de negócio para evitar reconstrução se houver outro grupo/tenant no futuro;
- `business_unit_id` apenas onde a entidade realmente pertence a uma unidade;
- datas em UTC e competência como mês civil explícito, não texto livre;
- valores monetários em decimal e moeda obrigatória;
- registros financeiros e auditoria não são fisicamente apagados;
- dados exibidos em uma NF são congelados em snapshot no momento da emissão;
- campos flexíveis em JSON somente para payload de integração e metadados, não para o núcleo relacional.

### 6.2 Organização e acesso

| Entidade | Finalidade |
|---|---|
| `organizations` | Grupo STK; prepara isolamento futuro sem construir SaaS |
| `business_units` | MR, Lab e Stelli; código único por organização |
| `users` / `profiles` | identidade humana |
| `roles`, `permissions`, `user_unit_roles` | schema pronto para múltiplos usuários; V1 usa apenas administrador |
| `service_accounts` | identidades de n8n, integração Python e agentes; nunca compartilhar conta humana |

Mesmo com apenas Thiago, autorização deve existir desde o primeiro endpoint. A interface completa de administração de papéis pode ser V2.

### 6.3 Pessoas e empresas

| Entidade | Observações |
|---|---|
| `people` | cadastro canônico do Grupo; CPF somente quando necessário |
| `companies` | cadastro canônico; CNPJ normalizado |
| `person_company_relationships` | papel, vigência e indicação de contato principal |
| `person_business_units` | relacionamento comercial da pessoa com cada unidade |
| `company_business_units` | relacionamento comercial da empresa com cada unidade |
| `contact_methods` | vários e-mails/telefones/WhatsApps, tipo, valor normalizado, verificação e preferência |
| `addresses` | endereço estruturado e reutilizável quando necessário |
| `duplicate_candidates` | pares suspeitos, score/motivos e decisão humana |
| `merge_history` | rastreia fusão de cadastros e permite explicar a origem |

Telefone/e-mail são sinais de identidade, não prova absoluta. E-mail familiar compartilhado, telefone corporativo ou número reciclado impedem `UNIQUE` global indiscriminado. CPF/CNPJ normalizado pode ter unicidade por organização quando presente, após definição de política e qualidade de importação.

### 6.4 CRM

| Entidade | Observações |
|---|---|
| `products_services` | catálogo por unidade, com status e código |
| `lead_sources` | origem editável, mas estável para relatórios |
| `loss_reasons` | motivo por unidade/pipeline |
| `pipelines` | tipo `sales` ou `operations`, unidade e versão/configuração |
| `pipeline_stages` | ordem, SLA opcional, estado ativo; código único por pipeline |
| `opportunities` | unidade, pipeline, estágio atual, estado aberto/ganho/perdido, valor e datas |
| `opportunity_contacts` | várias pessoas e seus papéis; evita limitar a uma pessoa |
| `opportunity_stage_history` | append-only, com ator, origem e motivo |
| `activities` | interações ocorridas; direção, canal, resumo e referências externas |
| `tasks` | ações futuras com prazo, responsável, status e prioridade |
| `opportunity_products` | um ou mais produtos/serviços e valores |

Regras:

- oportunidade deve ter ao menos pessoa ou empresa;
- perder exige motivo;
- ganhar/perder registra data e ator;
- oportunidade aberta exige tarefa futura apenas após o período de implantação definido, para não bloquear importações;
- mudar estágio e gerar histórico ocorre em uma única transação;
- reabrir negócio cria histórico explícito;
- “última interação”, “dias na etapa” e “próxima ação” são derivados.

### 6.5 Contratos e faturamento

| Entidade | Observações |
|---|---|
| `contracts` | empresa, unidade MR, número, vigência, estado, moeda e serviço |
| `contract_billing_rules` | periodicidade, dia, valor, vencimento, descrição, emissão e suspensão |
| `contract_contacts` | destinatários financeiros e papéis; não copiar e-mail solto sem vínculo |
| `billing_runs` | execução de uma competência; aberto, processando, concluído ou concluído com exceções |
| `billing_items` | contrato + competência, valor calculado, snapshot e estado |
| `invoice_requests` | tentativa lógica idempotente de emissão e referência externa |
| `invoices` | NFS-e confirmada, número, código de verificação, datas e estado fiscal |
| `documents` | arquivo privado, hash, tipo, classificação e retenção |
| `message_deliveries` | envio de NF por Outlook, destinatários, tentativas e confirmação técnica |

Chaves e invariantes obrigatórias:

- contrato: `(organization_id, internal_number)` único;
- item: `(contract_id, competence_month)` único permanentemente;
- solicitação: chave de idempotência única;
- NF externa: `(provider, external_id)` e, quando aplicável, identificador fiscal únicos;
- execução mensal: `(business_unit_id, competence_month, run_type)` única, salvo reprocessamento versionado;
- cancelamento não apaga nem libera a chave para nova duplicata; uma correção cria revisão/substituição ligada ao item original;
- não usar “última competência faturada” como fonte da verdade. Ela pode ser um cache; a existência dos itens por competência é a verdade.

Antes de codificar, devem ser definidas regras de pró-rata, reajuste, retenções, feriados, vencimento, contrato suspenso durante parte do mês e alterações retroativas.

### 6.6 Automação, integrações e auditoria

| Entidade | Observações |
|---|---|
| `workflow_definitions` | identidade lógica e dono de negócio |
| `workflow_versions` | configuração imutável, critérios e artefato/versionamento externo |
| `workflow_deployments` | versão + ambiente + modo de maturidade |
| `workflow_runs` | correlação, gatilho, início/fim, resultado e versão |
| `workflow_actions` | ação proposta/executada, classe de risco, ator e resultado |
| `exceptions` | tipo, severidade, contexto mínimo, responsável, SLA e resolução |
| `approval_requests` | somente para modos/ações que exigem aprovação |
| `inbox_events` | provedor + ID externo único, payload protegido e estado |
| `outbox_events` | evento a entregar, tentativas e próxima tentativa |
| `external_references` | IDs em Outlook, WhatsApp, Python e outros provedores |
| `audit_events` | append-only: ator, ação, entidade, origem, correlação e diferenças seguras |
| `ai_runs` | modelo, versão de prompt, finalidade, saída estruturada, confiança, custo e revisão |
| `import_jobs` / `import_errors` | importações reprodutíveis e auditáveis |

O “antes/depois” da auditoria deve excluir secrets e mascarar campos sensíveis. Para documentos e mensagens longas, registrar hash, classificação e referência; não copiar conteúdo integral para toda camada de log.

---

## 7. CRM único para três empresas

A combinação **unidades de negócio + pipelines separados** é adequada, com quatro correções:

1. Pessoa e empresa são canônicas no Grupo e podem se relacionar a várias unidades.
2. Oportunidade, contrato, tarefa e atividade recebem unidade explícita ou herdada de forma inequívoca.
3. Toda consulta parte de `organization_id`; políticas adicionais filtram unidade conforme o papel.
4. Dashboards consolidados somam dados já classificados por unidade, sem duplicar cadastros.

Estratégia de permissão futura:

- papel organizacional: administrador do Grupo;
- papel por unidade: gestor, comercial, atendimento, financeiro, leitura;
- permissões por capacidade: ver financeiro, exportar, executar workflow, resolver exceção, administrar integração;
- service accounts por integração, cada uma com escopo mínimo.

O isolamento deve ser aplicado no backend e reforçado no banco. Se Supabase for usado com Data API, todas as tabelas expostas precisam de grants restritos e RLS; a documentação alerta que tabelas expostas sem RLS podem ser acessadas por papéis com grants correspondentes. Ver [segurança da Data API](https://supabase.com/docs/guides/api/securing-your-api) e [Row Level Security](https://supabase.com/docs/guides/database/postgres/row-level-security).

Não recomendo três bancos nem três CRMs na V1. Isso inviabilizaria a visão consolidada e multiplicaria integrações. Também não recomendo preparar multi-tenancy comercial completa; basta incluir organização, isolamento e migrações disciplinadas.

---

## 8. Stack recomendada

### 8.1 Recomendação

| Camada | Escolha recomendada | Motivo |
|---|---|---|
| Frontend | React/Next.js, responsivo | ecossistema maduro, bom para Kanban e compatível com Lovable como acelerador |
| Backend | FastAPI/Python em serviço de contêiner gerenciado | contratos explícitos, validação, excelente integração com o sistema Python e desenvolvimento assistido pelo Codex |
| Banco | Supabase gerenciado/PostgreSQL, região São Paulo | Postgres real, Auth, Storage, APIs opcionais, velocidade e menor operação |
| Autenticação | Supabase Auth com MFA para administradores | evitar construir identidade; autorização continua no backend/banco |
| Documentos | bucket privado no Supabase Storage, links temporários | controle de acesso e separação do banco |
| Orquestração | n8n gerenciado ou self-hosted já existente, após avaliação de dados | bons conectores e velocidade de automação |
| IA | OpenAI via backend/n8n com saída estruturada e prompts versionados | classificação, extração e resumo auditáveis |
| Observabilidade | serviço gerenciado de erros + métricas e alertas | não construir plataforma própria de observabilidade |
| Código e deploy | Git, revisão e ambientes separados | Lovable/n8n não substituem versionamento e promoção |

Supabase é a melhor opção para a realidade descrita, **desde que não seja usado como desculpa para colocar toda lógica no frontend**. Ele fornece PostgreSQL dedicado, autenticação, Storage e APIs; há região específica de [São Paulo (`sa-east-1`)](https://supabase.com/docs/guides/platform/regions). Backups diários existem nos planos pagos e PITR é adicional; arquivos do Storage não fazem parte do backup do banco, portanto precisam de política própria. Ver [visão do banco](https://supabase.com/docs/guides/database/overview) e [backups](https://supabase.com/docs/guides/platform/backups).

### 8.2 Comparação resumida

| Alternativa | Pontos fortes | Limitações para este projeto | Parecer |
|---|---|---|---|
| Supabase gerenciado | menor tempo, Postgres, Auth/Storage, RLS, região SP | exige desenho cuidadoso de RLS; recursos gerenciados criam algum acoplamento | **Recomendado** |
| PostgreSQL gerenciado + backend + Auth separado | máximo controle e portabilidade | mais fornecedores, integração e operação | boa alternativa se compliance rejeitar Supabase |
| Firebase/Firestore | velocidade para apps orientados a documentos e realtime | modelo relacional e relatórios financeiros/CRM ficam menos naturais | não recomendado como núcleo |
| Backend completo customizado em nuvem | controle total | custo operacional e de segurança desnecessário na V1 | evitar |
| Supabase self-hosted | controle de infraestrutura | equipe passa a responder por backup, patch, disponibilidade e incidentes; a própria documentação de Lovable explicita essas responsabilidades | não usar na V1 sem requisito obrigatório |
| Lovable Cloud como stack completa | prototipação rápida | governança, regras e ciclo de engenharia podem ficar dependentes da plataforma | somente protótipo/frontend |

### 8.3 Backend separado é necessário?

Sim. Operações simples de leitura podem futuramente usar APIs geradas sob RLS, mas comandos críticos devem passar pelo backend: mover etapa, fundir contato, gerar competência, emitir NF, registrar pagamento, executar ação de agente e exportar dados. Supabase permite desativar a Data API caso todo acesso passe por servidor confiável, opção documentada em [Securing your API](https://supabase.com/docs/guides/api/securing-your-api).

---

## 9. Papel exato do n8n

### Deve ficar no n8n

- gatilhos agendados que chamam um comando do backend;
- coordenação de APIs externas;
- espera, polling e callback de integrações;
- roteamento por resultado já validado;
- transformação leve de payload;
- envio de Outlook/WhatsApp;
- chamada de IA para tarefas bem delimitadas;
- notificação de exceções;
- subworkflows reutilizáveis para conectores.

### Deve ficar no backend

- autenticação e autorização;
- regras de domínio e transições válidas;
- deduplicação e fusão de cadastros;
- elegibilidade e cálculo de faturamento;
- criação atômica de contrato + competência;
- chaves de idempotência;
- estado oficial de execução e exceção;
- auditoria oficial;
- política de autonomia e limites;
- validação de qualquer saída de IA;
- geração de links seguros para documentos.

### Não deve depender do n8n

- uso normal da interface;
- login e permissões;
- CRUD e busca;
- Kanban e histórico;
- proteção contra faturamento duplicado;
- cálculo financeiro;
- integridade referencial;
- decisão de que um agente pode executar uma ação;
- disponibilidade do histórico oficial.

### Regras de manutenção

- workflows pequenos e nomeados por capacidade, não um fluxo gigante;
- entradas e saídas com schema versionado;
- IDs de correlação e idempotência em toda chamada;
- ambientes e credenciais separados;
- exportação/versionamento dos workflows no Git;
- nenhuma credencial em nodes, prompts ou frontend;
- caminho de erro explícito e exceção persistida no STK OS;
- limitar dados salvos nas execuções e aplicar retenção/redação. O n8n documenta redaction de dados de execução e recomenda proteger dados de produção; ver [redação de execução](https://github.com/n8n-io/n8n-docs/blob/main/docs/deploy/host-n8n/configure-n8n/security/redact-execution-data.md).

---

## 10. Estratégia de IA

### Deve usar regra determinística

- normalização de CPF, CNPJ, telefone, e-mail e competência;
- correspondência exata e prevenção de duplicidade;
- validade, periodicidade, valor, vencimento e elegibilidade de contrato;
- permissões, limites e transições de estado;
- preço de catálogo, desconto permitido e cálculo de orçamento;
- disponibilidade real de agenda e confirmação;
- criação/registro fiscal, envio e conciliação;
- SLA, retry, circuit breaker e suspensão;
- seleção de unidade quando o canal/formulário já fornece essa informação.

### Deve usar IA

- classificação de intenção em texto livre de WhatsApp;
- classificação e resumo de e-mails não estruturados;
- extração de campos candidatos de documentos/textos livres;
- seleção de categoria quando regras e metadados não resolvem.

“Deve” significa que a funcionalidade só tem valor por interpretar linguagem não estruturada; não significa que toda saída pode produzir uma ação autônoma.

### Pode usar IA

- identificar unidade/interesse quando o canal não informa;
- sugerir próxima ação ou rascunho de resposta;
- priorizar possíveis duplicatas para revisão;
- resumir histórico extenso;
- sugerir lead score;
- recuperar conteúdo de base autorizada e redigir uma resposta limitada.

### Não deve usar IA

- decidir se pode faturar ou qual valor emitir;
- autorizar, cancelar ou substituir NF;
- fundir contatos automaticamente em casos ambíguos;
- definir permissão, base legal ou prazo de retenção;
- apagar dados;
- dar orientação clínica, interpretar resultado ou inventar preparo de exame;
- confirmar preço/agendamento sem consultar catálogo/agenda oficiais;
- executar ação financeira porque um e-mail pediu;
- tratar texto recebido como instrução de sistema.

### Controles obrigatórios

- saída estruturada por schema e validação no backend;
- prompt e modelo versionados;
- conjunto de avaliação com exemplos reais anonimizados;
- confiança somente quando calibrada para a tarefa; um número declarado pelo modelo não é probabilidade confiável por si só;
- regras de fallback e classe `não_sei`;
- entrada mínima necessária, com mascaramento quando possível;
- proteção contra prompt injection: mensagens e documentos são dados, nunca instruções;
- registro de finalidade, modelo, decisão, ação resultante e revisão, evitando payload integral em logs;
- teto de custo, timeout e rate limit;
- base autorizada com versão e validade do conteúdo.

Para STK Lab, a IA pode detectar a intenção, mas respostas sobre preparo, preço e políticas devem vir de conteúdo aprovado ou templates. Casos clínicos e linguagem de urgência devem ser encaminhados conforme política formal, nunca improvisados pelo modelo.

---

## 11. Estratégia de autonomia

### 11.1 Ciclo recomendado

1. **Desenvolvimento:** dados sintéticos, nenhuma credencial produtiva.
2. **Teste:** ambiente isolado, integrações sandbox/mocks, testes de falha e repetição.
3. **Validação em sombra:** processa casos reais e compara a decisão sem executar efeitos externos.
4. **Validação assistida:** executa em produção, mas ações de risco selecionadas pedem aprovação.
5. **Autônomo limitado:** somente versão, unidade, tipos de caso e limites aprovados.
6. **Autônomo ampliado:** escopo cresce após nova evidência.
7. **Suspenso:** kill switch manual ou automático; eventos continuam preservados para retomada controlada.

Os nomes do PRD podem ser mantidos, registrando sombra e assistido como modos da fase `VALIDAÇÃO`.

### 11.2 Critérios para promoção

Cada versão precisa declarar:

- universo de casos permitido;
- ações permitidas e proibidas;
- volume mínimo ou janela de observação;
- precisão por classe, não apenas média geral;
- taxa de exceção, erro e intervenção;
- zero duplicidade em efeitos financeiros;
- zero incidente de segurança/privacidade relevante;
- cobertura de cenários de falha e repetição;
- responsável de negócio que aprova a promoção;
- data de revisão/expiração da autorização.

Não adotar um threshold universal como “90%”. Classificações inofensivas podem tolerar erro maior; emissão fiscal exige invariantes determinísticas e confirmação do provedor, não confiança de IA.

### 11.3 Resiliência

- retries apenas para falhas transitórias, com espera exponencial e limite;
- todas as ações externas recebem chave de idempotência;
- erros permanentes vão para exceção/dead letter, não para loop infinito;
- circuit breaker suspende um conector após falhas ou anomalias repetidas;
- timeouts explícitos;
- reconciliação periódica consulta fonte externa para detectar estados divergentes;
- alertas por severidade e SLA;
- reprocessamento pelo ID original, nunca “executar tudo de novo” sem contexto.

### 11.4 Rollback

Em integrações externas, rollback técnico raramente desfaz o mundo real. Usar ações compensatórias:

- atividade incorreta: marcar como anulada mantendo histórico;
- e-mail enviado: não há rollback; impedir repetição e registrar incidente;
- NF emitida: seguir cancelamento/substituição fiscal formal;
- etapa movida: nova transição de correção;
- fusão de cadastros: histórico reversível e referências preservadas.

---

## 12. Segurança e LGPD

Esta seção é orientação técnica, não parecer jurídico. A base legal, papéis de controlador/operador, retenção e transferências devem ser validados com responsável jurídico/privacidade.

### 12.1 Controles mínimos antes de produção

- MFA para administrador e acessos de infraestrutura;
- identidades separadas para humano, n8n, Python e agentes;
- menor privilégio por unidade e capacidade;
- secrets somente em cofre/gerenciador do ambiente, com rotação;
- TLS em trânsito e criptografia do provedor em repouso;
- RLS/grants no banco e autorização no backend;
- arquivos privados; links curtos e assinados;
- auditoria append-only protegida contra alteração pelo usuário comum;
- backup automático, cópia lógica fora do projeto e teste de restauração;
- RPO/RTO definidos;
- inventário de fornecedores/suboperadores e contratos de tratamento;
- política de retenção e descarte por categoria;
- plano de resposta a incidente;
- varredura de anexos antes de uso/armazenamento operacional;
- dependências e imagens atualizadas;
- rate limits, validação de webhook e proteção contra replay;
- proibição de dados reais em desenvolvimento.

A ANPD define controle de acesso como autenticação, autorização e auditoria e recomenda níveis de permissão proporcionais. Também orienta backups regulares em local seguro e distinto. Ver o [Guia de Segurança da Informação da ANPD](https://www.gov.br/anpd/pt-br/documentos-e-publicacoes/guia-vf.pdf). Mesmo agentes de pequeno porte precisam adotar medidas técnicas e administrativas compatíveis com o risco, conforme a [Resolução CD/ANPD nº 2](https://www.gov.br/anpd/pt-br/acesso-a-informacao/institucional/atos-normativos/regulamentacoes_anpd/resolucao-cd-anpd-no-2-de-27-de-janeiro-de-2022).

### 12.2 STK Lab

Dados de saúde são sensíveis sob a LGPD. O CRM deve receber apenas o mínimo comercial/operacional:

- identificação e contato;
- intenção em categoria ampla;
- orçamento e status;
- data/horário operacional;
- consentimentos/preferências de canal quando aplicável;
- referência opaca ao sistema laboratorial, se indispensável.

Não armazenar no STK OS:

- resultados;
- laudos;
- diagnóstico, sintomas ou hipótese clínica;
- pedido médico ou imagem integral sem requisito validado;
- histórico clínico;
- resumo de conversa que reproduza informação de saúde desnecessária;
- embeddings de conteúdo clínico.

Campos “observações”, transcrições e logs são o maior caminho de vazamento desse limite. O Lab precisa de textos de ajuda aprovados, categorias fechadas e retenção curta de mensagens brutas. O sistema deve possibilitar retificação, exportação e descarte conforme política e obrigação aplicável. A definição legal e os princípios de tratamento constam na [LGPD compilada](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709compilado.htm).

### 12.3 IA e fornecedores

- documentar quais dados vão para OpenAI, n8n, WhatsApp, Outlook, Supabase e demais operadores;
- verificar DPA, subprocessadores, localização e retenção de cada serviço;
- não enviar base inteira ao modelo;
- mascarar CPF/CNPJ e dados financeiros quando não necessários;
- impedir acesso amplo de agentes ao banco; fornecer tools/comandos restritos;
- impedir exportação em massa por agente;
- registrar consentimento/aprovação somente quando juridicamente aplicável, sem usar “consentimento” como base genérica para tudo.

Supabase oferece região São Paulo, mas região de armazenamento não resolve sozinha toda a cadeia: subprocessadores, suporte, logs e serviços de IA devem entrar no registro de tratamento.

---

## 13. API e MCP

### Recomendação

**API primeiro; MCP fora da V1 inicial.**

A API é o contrato estável usado por frontend, n8n, sistema Python e futuros agentes. Deve oferecer comandos de negócio, não acesso genérico a tabelas. Exemplos conceituais: criar oportunidade, mover etapa, gerar competência, solicitar emissão, registrar entrega e resolver exceção.

Requisitos da API:

- autenticação de usuário e service account;
- autorização por unidade/capacidade;
- idempotência em comandos com efeito;
- validação de schema;
- versionamento compatível;
- correlação e auditoria;
- paginação, filtros e rate limit;
- erros de domínio previsíveis;
- documentação OpenAPI;
- nenhum endpoint genérico do tipo “execute SQL” ou “atualize qualquer campo”.

MCP é uma camada de adaptação para hosts de IA: servidores expõem tools, resources e prompts, e tools são controladas pelo modelo. A arquitetura oficial é baseada em host–client–server e negociação de capacidades; não substitui a API nem suas regras. Consulte a [arquitetura do MCP](https://modelcontextprotocol.io/specification/2025-06-18/architecture) e a [visão de primitives do servidor](https://modelcontextprotocol.io/specification/2025-06-18/server/index).

Quando houver um caso real de agente externo, criar um servidor MCP fino que traduz tools estreitas para a API existente. Começar apenas com leitura e ações reversíveis; ações financeiras continuam sujeitas à política do backend. Construir MCP agora duplicaria contratos, autenticação e testes antes de existir consumidor comprovado.

---

## 14. Integração com o sistema Python atual

### Decisão recomendada

**Preservar o emissor e envolvê-lo em uma API interna autenticada**, preferencialmente assíncrona.

Contrato mínimo do adaptador:

- receber solicitação com chave de idempotência e snapshot fiscal;
- devolver identificador da solicitação rapidamente;
- informar estados `recebida`, `processando`, `emitida`, `rejeitada` ou `incerta`;
- retornar número/código da NF e referência segura ao documento;
- permitir consultar o estado;
- notificar conclusão por webhook assinado ou ser consultado pelo n8n;
- não emitir novamente para a mesma chave;
- registrar versão do emissor e resposta do provedor, sem expor credenciais.

Fluxo:

1. Backend gera item por contrato/competência em transação.
2. n8n solicita emissão ao adaptador com a chave do item.
3. Adaptador verifica a chave antes de chamar o provedor.
4. Resultado volta por callback ou polling.
5. Backend valida e registra a NF.
6. Somente após confirmação, n8n envia o e-mail.
7. Reconciliação verifica solicitações em estado incerto.

Não usar acesso direto ao banco do sistema Python, chamada de script por arquivo compartilhado ou automação de interface como integração principal. Uma fila pode ser adicionada internamente ao adaptador se a emissão for lenta; não é necessário expor essa tecnologia ao restante do STK OS.

Antes da decisão final é obrigatória uma inspeção técnica do sistema atual: implantação, dependências, provedor municipal, formatos, tratamento de erros, armazenamento de certificado, concorrência e possibilidade real de idempotência. Reescrever só será justificável se o código não puder ser isolado ou operado com segurança.

---

## 15. Revisão dos quatro workflows prioritários

### 15.1 Faturamento recorrente MR — primeiro a implementar

**Manter como primeiro workflow**, com alteração de responsabilidade.

Fluxo recomendado:

1. Scheduler solicita ao backend a criação da execução da competência.
2. Backend seleciona contratos elegíveis e cria itens únicos numa transação.
3. Itens inválidos viram exceções antes de qualquer emissão.
4. n8n percorre itens prontos e chama o adaptador Python.
5. Cada solicitação usa idempotência.
6. Resultado confirmado cria/atualiza NF no backend.
7. Documento é armazenado de forma privada e verificado por hash.
8. n8n envia pelo Outlook ao contato financeiro congelado para aquela competência.
9. Envio e falha são registrados.
10. Reconciliação fecha a execução ou aponta exceções.

Critérios de autonomia: zero duplicidade, reconciliação completa, todos os casos incertos encaminhados, dados obrigatórios validados e comportamento testado para repetição/timeout. A emissão não usa IA.

### 15.2 Lead → CRM Grupo — segundo incremento

Fluxo recomendado:

1. Canal envia evento autenticado.
2. Inbox persiste e deduplica o evento do provedor.
3. Normalização determinística de contato.
4. Correspondência exata segura atualiza o cadastro; ambiguidade cria candidato a duplicata.
5. Unidade/interesse vêm do canal/regra; IA é fallback.
6. Backend cria oportunidade somente se regra de oportunidade equivalente não encontrar uma aberta.
7. Tarefa futura é criada.
8. Tudo registra origem, versão da classificação e correlação.

Não fazer merge autônomo por similaridade de nome. “Nenhum lead sem acompanhamento” deve ser medido por evento recebido versus oportunidade/tarefa ou exceção criada.

### 15.3 Atendimento STK Lab — depois da política de dados e provedor

Fluxo recomendado:

1. Usar provedor oficial de WhatsApp Business; não construir transporte próprio.
2. Persistir mensagem mínima e vínculo de conversa.
3. Regra identifica casos simples por botão/template; IA classifica texto livre.
4. Policy engine decide se a intenção pode ser atendida automaticamente.
5. Resposta usa catálogo/base aprovada e dados atuais de preço/agenda.
6. Confirmação de agenda ocorre somente no sistema oficial com controle de concorrência.
7. Sinais clínicos, urgência, pedido de interpretação, baixa confiança ou falha de fonte vão para humano.
8. CRM guarda resumo comercial mínimo, não transcrição clínica.

Na V1 inicial, limitar a FAQ, preço, localização, horário e encaminhamento. Orçamento e agendamento autônomos entram depois que catálogo e agenda forem fontes confiáveis.

### 15.4 E-mails/documentos MR — inicialmente somente triagem

Fluxo recomendado:

1. Microsoft Graph/webhook sinaliza mensagem; endpoint valida e persiste o ID.
2. Conteúdo e anexos necessários são buscados com menor permissão possível.
3. Correspondência do remetente é sinal, não prova de cliente/processo.
4. IA classifica, resume e extrai datas como candidatas.
5. Backend valida categoria e cria atividade/tarefa.
6. Anexos passam por política de tipo/tamanho e varredura.
7. V1 não responde, protocola, aceita obrigação ou executa ação financeira automaticamente.

Deduplicar por IDs do Microsoft Graph/Internet Message ID. Datas e obrigações extraídas precisam de revisão até a avaliação demonstrar confiabilidade por categoria.

---

## 16. Escopo final recomendado para a V1

### V1 obrigatória

- autenticação do único administrador com MFA;
- organização e três unidades;
- schema de papéis/service accounts, mesmo sem telas completas;
- pessoas, empresas, vínculos e métodos de contato;
- oportunidades, pipelines, estágios, histórico, atividades e tarefas;
- pipelines comerciais corrigidos, sem ganho/perda como etapa;
- contratos MR e regra de faturamento;
- execução, item por competência, solicitação, NF, documento e envio;
- unicidade e idempotência no banco/backend;
- API do backend para frontend e n8n;
- inbox/outbox, auditoria e fila de exceções;
- Kanban, cadastros, busca essencial e visão 360° enxuta;
- painel operacional de CRM e faturamento, com definições de métricas;
- importação controlada de clientes/contratos/leads ativos;
- integração API com sistema Python e Outlook;
- primeiro workflow de faturamento em validação e depois autonomia limitada;
- ambientes separados, backups e teste de restauração;
- política mínima LGPD e de retenção.

### V1 opcional, se não atrasar o faturamento

- captura automática de um único canal de lead;
- classificação de unidade/interesse para leads não identificados;
- dashboard básico de workflows;
- uso de Lovable para acelerar frontend;
- importação de bases de reativação;
- filtros e refinamentos adicionais do dashboard.

### V2

- Lead → CRM completo e múltiplos canais;
- triagem de e-mail MR com tarefas;
- atendimento Lab limitado a FAQ e encaminhamento;
- múltiplos usuários, UI de papéis e isolamento por unidade;
- agendamento integrado;
- dashboard de automação e métricas de IA;
- regras de renovação contratual;
- propostas/documentos mais estruturados;
- recebíveis, boleto Itaú, pagamentos e cobrança após desenho financeiro.

### V3

- MCP para consumidores de IA comprovados;
- agentes especializados com capacidades graduais;
- autonomia ampliada nos workflows 2–4;
- ROI/horas liberadas com telemetria confiável;
- customer success, pedidos/entrega Stelli e operações pós-venda próprias;
- módulos Ambiental/Regulatório, somente com PRDs separados;
- analytics avançado e modelos preditivos se houver volume.

### Remover ou reformular

- etapa “Ganho/Perdido” dentro de pipelines;
- campo único de unidade em pessoa/empresa;
- n8n escrevendo diretamente em tabelas de negócio;
- exclusão física comum de registros auditáveis;
- MCP como requisito de V1;
- equivalência irrestrita entre permissões humanas e agentes;
- armazenamento indiscriminado de observações/transcrições do Lab;
- `última_competência_faturada` como mecanismo de controle;
- quatro workflows completos como condição da primeira entrega;
- construção de autenticação, transporte de WhatsApp, emissor fiscal, calendário ou observabilidade próprios.

---

## 17. Roadmap técnico sugerido

### Marco 0 — decisões e descoberta

- responder às perguntas bloqueantes;
- inspecionar sistema Python e integrações disponíveis;
- mapear dados pessoais, finalidade, retenção e fornecedores;
- fechar glossário de estados e métricas;
- registrar decisões arquiteturais e ameaça inicial;
- validar protótipo do modelo de faturamento com exemplos reais.

**Saída:** arquitetura, modelo e contratos aprovados; só então iniciar código de produção.

### Marco 1 — fundação

- ambientes, identidade, organização/unidades e migrações;
- backend, autorização, auditoria, inbox/outbox e exceções;
- CI/CD, secrets, backup, restore e observabilidade;
- contrato da API e service accounts.

### Marco 2 — CRM operacional

- cadastros, vínculos, oportunidades, tarefas e histórico;
- Kanban, busca e visão 360° enxuta;
- importação das prioridades 1–3;
- métricas básicas validadas.

### Marco 3 — financeiro MR e adaptador Python

- contratos, regras, execuções e itens;
- API idempotente do sistema Python;
- documentos privados e envio Outlook;
- reconciliação e painel de exceções.

### Marco 4 — validação e autonomia do faturamento

- testes de repetição, timeout, retorno incerto e falha parcial;
- sombra e aprovação assistida;
- métricas de confiabilidade;
- autonomia limitada com circuit breaker e kill switch.

### Marco 5 — automações seguintes, uma por vez

1. Lead → CRM;
2. triagem de e-mail MR;
3. Lab FAQ/handoff;
4. orçamento/agendamento Lab após fontes oficiais.

Cada incremento repete o ciclo de teste, sombra, validação e autonomia. Não iniciar o seguinte antes de o anterior ter dono, métrica e operação de exceções.

---

## 18. Perguntas bloqueantes antes de escrever código

1. **Entidades e LGPD:** quais pessoas jurídicas serão controladoras dos dados de MR, Lab e Stelli? Haverá compartilhamento formal no Grupo? Quem decide retenção e atende titulares?
2. **Isolamento:** usuários futuros poderão pertencer a várias unidades? Financeiro será visível por unidade, papel ou empresa jurídica?
3. **Sistema Python:** onde roda, como é acionado hoje, qual provedor/município atende, como guarda certificado e credenciais, e já possui API ou chave de idempotência?
4. **Regra fiscal/contratual:** como tratar pró-rata, reajuste, retenções, suspensão parcial, retroativos, alterações de valor, feriados, vencimento e substituição/cancelamento de NF?
5. **Competência:** é sempre mês calendário? Qual timezone e qual regra para contrato iniciado/encerrado no meio do mês?
6. **Fonte do contrato:** quem cria/aprova contrato e alteração de regra de faturamento? Uma mudança vale para a competência aberta ou somente para a próxima?
7. **Volumes e confiabilidade:** quantos contatos, contratos, mensagens, e-mails e documentos existem/entram por mês? Quais RPO, RTO e SLA são aceitáveis?
8. **Hospedagem e orçamento:** há restrição de região, fornecedor, self-hosting ou custo mensal? Supabase São Paulo e n8n gerenciado são aceitáveis após análise contratual?
9. **n8n:** já existe instância? Quem administra atualizações, backups, credenciais e incidentes?
10. **Outlook:** qual tenant Microsoft 365 e quais caixas serão usadas? Há autorização para Microsoft Graph e mailbox dedicada para automação?
11. **WhatsApp:** qual provedor oficial será usado? Número, templates, regras de janela, consentimento e handoff já estão definidos?
12. **Agenda e catálogo Lab:** qual é a fonte oficial de horários, exames, preparos e preços? Quem aprova e atualiza o conteúdo?
13. **Limite clínico:** quais categorias e campos são expressamente permitidos no CRM do Lab, e qual procedimento ocorre quando o cliente envia espontaneamente dado de saúde?
14. **Pipelines:** Lab e Stelli usarão um pipeline operacional misto temporariamente ou a V1 encerrará oportunidade em ganho e acompanhará execução fora do CRM?
15. **Deduplicação:** em caso de conflito entre CPF, e-mail e telefone, quem revisa? Quais fontes importadas são consideradas confiáveis?
16. **Documentos:** por quanto tempo guardar NFs, anexos de e-mail, mensagens e logs? Quais arquivos exigem cópia oficial fora do Outlook?
17. **Autonomia:** quem é o dono de negócio autorizado a promover/suspender cada workflow e quais ações nunca poderão ser autônomas?
18. **Métricas:** definição exata de lead, oportunidade, conversão, faturado, enviado, comparecimento e abandono para evitar dashboards divergentes.

---

## Parecer final

# NÃO APROVADO PARA IMPLEMENTAÇÃO

Antes de iniciar código de produção, precisam ser resolvidas e registradas estas decisões:

1. backend como dono das regras e n8n sem gravação direta no núcleo;
2. modelo de pessoa/empresa multiunidade e política de autorização;
3. separação entre estado da oportunidade e etapas, especialmente Lab/Stelli;
4. modelo financeiro e regras de competência/correção;
5. contrato idempotente do sistema Python após inspeção;
6. stack, ambientes, hospedagem, backup e recuperação;
7. política LGPD e limite técnico dos dados do Lab;
8. política versionada de autonomia, exceções e kill switch;
9. provedores/permissões de Outlook, WhatsApp e agenda;
10. corte formal da primeira entrega: CRM + faturamento MR; demais workflows sequenciais.

Resolvidos esses pontos, o projeto pode ser aprovado sem alterar sua visão estratégica. O problema não é a viabilidade do STK OS; é impedir que uma boa visão seja implementada sobre fronteiras ambíguas e depois precise ser reconstruída.
