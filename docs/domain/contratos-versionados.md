# Contratos versionados

## Agregados

O contrato separa identidade administrativa de configuração temporal:

- `contracts`: identidade, cliente, unidade, datas básicas, responsável e status administrativo;
- `contract_versions`: snapshot completo da configuração a partir de uma data;
- `contract_version_services`: serviços incluídos ou excluídos no snapshot;
- `contract_version_contacts`: contatos financeiros canônicos e sua função;
- `contract_operational_events`: suspensão, retomada, rescisão e renovação.

Não existem nesta etapa competências, cobranças, parcelas, recebimentos, documentos fiscais ou automações externas.

## Linha do tempo das versões

A primeira versão é `initial`, tem número 1 e começa em `contract.start_date`. Toda nova versão tem número sequencial e `effective_from` posterior ao início da última versão. O fluxo normal não aceita data retroativa.

O fim de uma versão não é armazenado: para consulta, `effective_until = próxima.effective_from - 1 dia`. A última versão não possui fim. Essa regra produz exatamente uma configuração por data a partir do início do contrato, sem lacunas ou sobreposição.

Uma versão futura fica agendada. Quando a data chega, ela passa a ser a configuração corrente sem mutação da versão anterior. Versões cujo fim derivado já passou são históricas. O endpoint de configuração aceita uma data arbitrária e usa o mesmo algoritmo.

Cada criação recebe um snapshot completo de moeda, valor, recorrência, vencimento, vencimento operacional, forma de pagamento, condições de reajuste, observações, emissor, serviços e contatos. Exclusão de serviço é uma linha inativa no snapshot, nunca uma remoção histórica.

## Estados independentes

O status administrativo é `draft`, `active` ou `archived`. Ele descreve a administração do cadastro, não a operação temporal.

O estado operacional é derivado dos eventos:

- sem evento aplicável ou após `resumed`: ativo;
- após `suspended`: suspenso;
- após `terminated`: encerrado.

`renewed` registra o fato de renovação e referencia a versão `renewal`; não cria um quarto estado operacional. Eventos são cronológicos, futuros ou presentes, e append-only.

## Relacionamentos e isolamento

O cliente é uma `company` canônica do CRM com vínculo ativo à unidade do contrato. Serviços vêm do catálogo da mesma organização e unidade. Contatos são `contact_methods` ativos do cliente ou de pessoa com relacionamento ativo com ele. O emissor é um `fiscal_establishment` ativo pertencente à organização, podendo ser diferente do estabelecimento operacional da unidade.

Capacidades distinguem leitura, criação, versionamento e eventos operacionais. Papéis limitados a unidades só leem e alteram contratos dentro do próprio escopo. A API e gatilhos PostgreSQL verificam organização, unidade e ator.

## Imutabilidade e correção

Versões, seus serviços, seus contatos e eventos operacionais rejeitam `UPDATE` e `DELETE`. Ajustes normais criam nova versão; nunca sobrescrevem a anterior. Correção histórica não foi implementada: ela exigirá fluxo futuro com autorização elevada, motivo obrigatório e evidência auditável.

Toda escrita relevante é idempotente, correlacionada, auditada e acompanhada por evento de outbox na mesma transação.
