# ADR 0005 — Trilha de controle transacional

- Status: aceito
- Data: 2026-08-19

## Decisão

Cada comando relevante recebe correlação, autenticação e idempotência. A mudança, a auditoria append-only e o evento de outbox são confirmados na mesma transação. Inbox deduplica por origem e identificador externo; exceções nunca armazenam secrets ou payload integral por padrão.

## Consequências

Repetições podem ser tratadas com segurança e a auditoria oficial não depende de logs técnicos ou ferramentas externas.

