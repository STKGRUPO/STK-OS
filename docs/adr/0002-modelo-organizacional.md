# ADR 0002 — Modelo organizacional e fiscal

- Status: aceito
- Data: 2026-08-19

## Decisão

Modelar explicitamente `Grupo → Entidade Jurídica → Estabelecimento Fiscal → Unidade de Negócio`. Unidade de negócio não representa CNPJ, matriz ou filial.

## Consequências

Contratos futuros poderão referenciar `issuer_establishment_id` sem usar unidade comercial ou nome textual como emissor. A fundação não cria antecipadamente tabelas financeiras.

