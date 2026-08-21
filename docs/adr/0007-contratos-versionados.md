# ADR 0007 — Contratos com configuração versionada e imutável

- Status: aceito
- Data: 2026-08-20

## Contexto

Um contrato precisa manter sua identidade administrativa estável e, ao mesmo tempo, preservar a configuração comercial válida em cada data. Alterações de valor, vencimento, serviços, emissor e contatos não podem apagar o passado nem antecipar os domínios financeiros das etapas seguintes.

## Decisão

`Contract` guarda a identidade administrativa: organização, unidade, cliente canônico, número interno, datas básicas, tipo, responsável e status administrativo. `ContractVersion` é um snapshot completo, numerado, temporal e append-only da configuração contratual.

Cada versão informa somente `effective_from`. Seu fim de vigência é derivado como o dia anterior ao início da versão seguinte. A primeira versão começa na data inicial do contrato; versões seguintes são estritamente crescentes e não podem ser retroativas no fluxo normal. Assim, a linha do tempo não admite sobreposição nem lacunas. Correção histórica dependerá de um futuro fluxo excepcional, explicitamente autorizado e auditado.

Valor monetário usa `numeric`/`Decimal`. Serviços e contatos financeiros são snapshots filhos da versão; uma nova versão não altera os registros anteriores. O emissor é um estabelecimento fiscal da mesma organização, independente da unidade comercial. Contatos continuam canônicos no CRM e somente são referenciados pela versão.

Suspensão, retomada, rescisão e renovação são fatos operacionais append-only em uma linha do tempo própria. Eles não reescrevem versão nem confundem estado operacional com status administrativo. Renovação referencia obrigatoriamente uma versão de tipo `renewal`.

Todas as escritas passam por capacidade e escopo de unidade, idempotência, correlação, auditoria e outbox na mesma transação. Gatilhos PostgreSQL reforçam isolamento organizacional, cronologia e imutabilidade mesmo fora da API.

## Consequências

- qualquer data pode resolver uma única configuração contratual histórica, atual ou futura;
- faturamento futuro poderá consultar a versão vigente sem reconstruir alterações;
- valores, emissores, serviços e contatos antigos permanecem comprováveis;
- mudança normal retroativa é rejeitada, não reinterpretada silenciosamente;
- a Etapa 4 não cria competência financeira, cobrança, parcela, nota fiscal ou integração externa.
