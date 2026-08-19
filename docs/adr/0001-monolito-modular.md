# ADR 0001 — Monólito modular

- Status: aceito
- Data: 2026-08-19

## Decisão

Usar Next.js no frontend, FastAPI no backend e PostgreSQL como fonte oficial, mantendo domínio, autorização e transações no backend. O worker será outro processo do mesmo código de backend.

## Consequências

Transações permanecem simples e os contratos ficam centralizados. Serviços separados só surgirão com necessidade concreta de escala ou isolamento.

