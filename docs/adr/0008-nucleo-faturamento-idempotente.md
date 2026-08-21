# ADR 0008 — Núcleo de faturamento mensal idempotente

- Status: aceito
- Data: 2026-08-20

## Contexto

A Etapa 5 precisa transformar contratos versionados em obrigações financeiras explicáveis sem emitir NFS-e. A operação deve resistir a repetição, concorrência, falhas isoladas e mudanças contratuais posteriores. Parte do Gate A continua sem decisão: centavos residuais de anual÷12, efeitos de versões e eventos dentro do mês, correção, cancelamento e estorno lógico.

## Decisão

Competência é um mês civil recebido na API como `YYYY-MM` e armazenado como `date` no primeiro dia do mês, com constraint que rejeita outro dia. O timezone operacional é IANA, explícito e configurável; o baseline atual é `America/Sao_Paulo`. Instantes permanecem `timestamptz`.

`billing_runs` identifica uma única execução lógica por organização, unidade e competência. `billing_run_contracts` congela a explicação de cada contrato considerado: obrigação criada, reutilizada ou contrato não elegível. `billing_items` guarda a obrigação única por `(contract_id, competence_month)`, a versão aplicada, emissor, cliente, valor `numeric`, snapshot JSON canônico e SHA-256.

A geração usa lock consultivo transacional no PostgreSQL por organização/unidade/competência. Constraints únicas permanecem como última linha de defesa. Repetições com outra chave técnica reutilizam o mesmo lote; a chave de negócio não expira. A idempotência HTTP de faturamento é retida por dez anos, sem substituir a invariante permanente.

O estado da obrigação é `blocked`, `ready`, `requested`, `completed` ou `cancelled`. Esta etapa só cria `blocked` ou `ready`; os demais estados reservam transições reais para etapas posteriores. `ready` significa apenas que o item satisfaz as regras contratuais aprovadas e pode futuramente ser solicitado ao serviço fiscal. Não significa NFS-e emitida.

Contrato iniciado depois do primeiro dia não gera obrigação na competência. Contrato suspenso ou encerrado no início e sem evento posterior no mês é não elegível. Versão ou evento operacional depois do primeiro dia e dentro do mês bloqueia o item por Gate A, sem pró-rata. Valor mensal usa o valor publicado; anual cobrado mensalmente usa anual÷12 somente quando o valor em centavos é divisível exatamente por 12. Qualquer resíduo bloqueia o item, sem arredondamento inventado.

Snapshot financeiro e seus campos explicativos não podem ser alterados. Correção, cancelamento e estorno lógico não foram inferidos. O reprocessamento seguro apenas recupera a execução já congelada; não corrige nem substitui obrigação.

## Consequências

- duas execuções ou workers não criam duas obrigações para o mesmo contrato/mês;
- falha ou ambiguidade de um contrato não invalida os demais;
- contratos não elegíveis e itens bloqueados permanecem explicáveis;
- alteração futura de contrato não modifica obrigação existente;
- `billing.item.ready.v1` é publicado na outbox sem chamar serviço fiscal;
- regras pendentes do Gate A ficam visíveis como bloqueio operacional;
- emissão, tributos, retenções, documentos, certificado e integrações continuam fora desta etapa.
